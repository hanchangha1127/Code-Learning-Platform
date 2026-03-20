from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    AIAnalysis,
    AnalysisType,
    Problem,
    ProblemDifficulty,
    ProblemKind,
    Submission,
    SubmissionStatus,
)
from app.services.ai_providers.platform_mode_bridge import get_platform_mode_ai_bridge
from app.services.problem_stat_service import update_user_problem_stat
from backend.ai_fallback import build_ai_evaluation_fallback, extract_analysis_error_detail
from backend.mode_normalization import (
    normalize_code_blame_commit_reviews as _shared_normalize_code_blame_commit_reviews,
    normalize_code_blame_commits as _shared_normalize_code_blame_commits,
    normalize_code_blame_facets as _shared_normalize_code_blame_facets,
    normalize_str_list as _shared_normalize_str_list,
    select_weighted_count as _shared_select_weighted_count,
)
from backend.mode_policies import (
    CLIENT_TO_PLATFORM_DIFFICULTY,
    CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY,
    CODE_BLAME_CULPRIT_COUNT_WEIGHTS,
    CODE_BLAME_FACET_TAXONOMY,
    CODE_BLAME_OPTION_IDS,
    MODE_PASS_THRESHOLD,
)
from backend.security import generate_token

CODE_BLAME_PASS_THRESHOLD = MODE_PASS_THRESHOLD
CODE_BLAME_TRACK_ID = "algorithms"

_DIFFICULTY_TO_DB: dict[str, ProblemDifficulty] = {
    key: ProblemDifficulty(value) for key, value in CLIENT_TO_PLATFORM_DIFFICULTY.items()
}

_mode_ai = get_platform_mode_ai_bridge()
_generator = _mode_ai
_ai_client = _mode_ai


def map_code_blame_difficulty(difficulty: str) -> ProblemDifficulty:
    normalized = (difficulty or "").strip().lower()
    mapped = _DIFFICULTY_TO_DB.get(normalized)
    if not mapped:
        raise ValueError("difficulty must be one of: beginner, intermediate, advanced")
    return mapped


def _normalized_difficulty(difficulty: str) -> str:
    normalized = (difficulty or "").strip().lower()
    if normalized not in _DIFFICULTY_TO_DB:
        raise ValueError("difficulty must be one of: beginner, intermediate, advanced")
    return normalized


def _candidate_count_for_difficulty(difficulty: str) -> int:
    normalized = _normalized_difficulty(difficulty)
    return CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY[normalized]


def select_code_blame_culprit_count() -> int:
    return _shared_select_weighted_count(count_weights=CODE_BLAME_CULPRIT_COUNT_WEIGHTS)


def _normalize_str_list(value: Any) -> list[str]:
    return _shared_normalize_str_list(value)


def _normalize_commits(value: Any, candidate_count: int) -> list[dict[str, str]]:
    return _shared_normalize_code_blame_commits(
        value,
        candidate_count=candidate_count,
        option_ids=CODE_BLAME_OPTION_IDS,
        missing_title_template="Commit {option_id}",
        missing_diff="diff --git a/app.py b/app.py\n@@\n+pass",
    )


def _validate_selected_commits(value: Any, option_ids: list[str], *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        if allow_empty:
            return []
        raise ValueError("selectedCommits must be an array")

    normalized: list[str] = []
    allowed = set(option_ids)
    for entry in value:
        token = str(entry or "").strip().upper()
        if token not in allowed:
            if allow_empty:
                continue
            raise ValueError("selectedCommits must contain only valid commit IDs")
        if token in normalized:
            if allow_empty:
                continue
            raise ValueError("selectedCommits must not contain duplicates")
        normalized.append(token)

    if not normalized and not allow_empty:
        raise ValueError("selectedCommits must contain at least one commit")
    if len(normalized) > 2:
        raise ValueError("selectedCommits must contain up to 2 commits")
    return normalized


def _normalize_commit_reviews(value: Any, option_ids: list[str]) -> list[dict[str, str]]:
    return _shared_normalize_code_blame_commit_reviews(
        value,
        option_ids=option_ids,
        missing_summary_template="{option_id} commit risk summary unavailable.",
    )


def _normalize_decision_facets(value: Any) -> list[str]:
    return _shared_normalize_code_blame_facets(
        value,
        taxonomy=CODE_BLAME_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )


def create_code_blame_problem(
    db: Session,
    *,
    user_id: int,
    language: str,
    difficulty: str,
) -> dict[str, Any]:
    normalized_language = (language or "").strip().lower()
    if not normalized_language:
        raise ValueError("language is required")

    normalized_difficulty = _normalized_difficulty(difficulty)
    mapped_difficulty = map_code_blame_difficulty(normalized_difficulty)
    candidate_count = _candidate_count_for_difficulty(normalized_difficulty)
    culprit_count = select_code_blame_culprit_count()

    generator_problem_id = generate_token("pblame")
    try:
        generated = _generator.generate_code_blame_problem_sync(
            problem_id=generator_problem_id,
            track_id=CODE_BLAME_TRACK_ID,
            language_id=normalized_language,
            difficulty=normalized_difficulty,
            mode="code-blame",
            candidate_count=candidate_count,
            culprit_count=culprit_count,
            decision_facets=list(CODE_BLAME_FACET_TAXONOMY),
            history_context=None,
        )
    except Exception as exc:
        raise ValueError("문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    title = str(generated.get("title") or "").strip() or "범인 찾기 문제"
    error_log = str(generated.get("error_log") or "").rstrip()
    prompt = str(generated.get("prompt") or "").strip() or "에러 로그와 diff를 비교해 범인 커밋을 추리하세요."
    commits = _normalize_commits(generated.get("commits"), candidate_count)
    option_ids = [row["optionId"] for row in commits]

    culprit_commits = _validate_selected_commits(generated.get("culprit_commits") or [], option_ids, allow_empty=True)
    if culprit_count == 1:
        culprit_commits = culprit_commits[:1]
    else:
        culprit_commits = culprit_commits[:2]
    if not culprit_commits:
        culprit_commits = option_ids[: min(culprit_count, len(option_ids))]
    if culprit_count == 2 and len(culprit_commits) < 2 and len(option_ids) >= 2:
        culprit_commits = option_ids[:2]

    decision_facets = _normalize_decision_facets(generated.get("decision_facets"))
    commit_reviews = _normalize_commit_reviews(generated.get("commit_reviews"), option_ids)
    reference_report = str(generated.get("reference_report") or "").strip()
    if not reference_report:
        reference_report = (
            f"범인 커밋은 {', '.join(culprit_commits)}입니다. "
            "로그와 diff 근거를 연결해 장애 메커니즘과 영향 범위를 설명하세요."
        )

    problem = Problem(
        kind=ProblemKind.code_blame,
        title=title,
        description=prompt,
        difficulty=mapped_difficulty,
        language=normalized_language,
        starter_code=error_log,
        options={
            "commits": commits,
            "culprit_commits": culprit_commits,
            "decision_facets": decision_facets,
            "reference_report": reference_report,
            "commit_reviews": commit_reviews,
            "candidate_count": candidate_count,
            "culprit_count": len(culprit_commits),
            "client_difficulty": normalized_difficulty,
        },
        answer_index=None,
        reference_solution=reference_report or None,
        is_published=False,
        created_by=user_id,
    )
    db.add(problem)
    db.commit()
    db.refresh(problem)

    return {
        "problemId": str(problem.id),
        "title": title,
        "language": normalized_language,
        "difficulty": normalized_difficulty,
        "errorLog": error_log,
        "commits": commits,
        "prompt": prompt,
        "decisionFacets": decision_facets,
    }


def submit_code_blame_report(
    db: Session,
    *,
    user_id: int,
    problem_id: str,
    selected_commits: list[str],
    report: str,
) -> dict[str, Any]:
    try:
        parsed_problem_id = int(str(problem_id).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("problemId is invalid") from exc

    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("report must not be empty")
    if len(normalized_report) > 12000:
        raise ValueError("report must be <= 12000 chars")

    problem = db.get(Problem, parsed_problem_id)
    if not problem or problem.kind != ProblemKind.code_blame:
        raise ValueError("problemId is invalid")
    if problem.created_by is not None and int(problem.created_by) != int(user_id):
        raise ValueError("problemId is invalid")

    options = problem.options if isinstance(problem.options, dict) else {}
    candidate_count = int(options.get("candidate_count") or len(options.get("commits") or []) or 3)
    commits = _normalize_commits(options.get("commits"), candidate_count)
    option_ids = [row["optionId"] for row in commits]

    normalized_selected_commits = _validate_selected_commits(selected_commits, option_ids)
    culprit_commits = _validate_selected_commits(options.get("culprit_commits") or [], option_ids, allow_empty=True)
    if not culprit_commits:
        culprit_commits = option_ids[:1]
    if len(culprit_commits) > 2:
        culprit_commits = culprit_commits[:2]

    decision_facets = _normalize_decision_facets(options.get("decision_facets"))
    reference_report = str(options.get("reference_report") or problem.reference_solution or "").strip()
    commit_reviews = _normalize_commit_reviews(options.get("commit_reviews"), option_ids)
    difficulty_for_ai = str(options.get("client_difficulty") or "intermediate")

    try:
        evaluation = _ai_client.analyze_code_blame_report(
            error_log=str(problem.starter_code or ""),
            prompt=str(problem.description or ""),
            commits=commits,
            selected_commits=normalized_selected_commits,
            culprit_commits=culprit_commits,
            report=normalized_report,
            decision_facets=decision_facets,
            reference_report=reference_report,
            commit_reviews=commit_reviews,
            language=str(problem.language or ""),
            difficulty=difficulty_for_ai,
        )
    except Exception as exc:
        evaluation = build_ai_evaluation_fallback(
            missed_types=decision_facets,
            error=exc,
        )

    score_raw = evaluation.get("score")
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))
    verdict = "passed" if score >= CODE_BLAME_PASS_THRESHOLD else "failed"
    is_correct = verdict == "passed"

    feedback = {
        "summary": str(evaluation.get("summary") or ""),
        "strengths": _normalize_str_list(evaluation.get("strengths")),
        "improvements": _normalize_str_list(evaluation.get("improvements")),
    }

    expected_set = set(decision_facets)
    found_types: list[str] = []
    for token in _normalize_str_list(evaluation.get("found_types")):
        lowered = token.lower()
        if lowered not in expected_set or lowered in found_types:
            continue
        found_types.append(lowered)
    if not found_types and decision_facets:
        report_lower = normalized_report.lower()
        for token in decision_facets:
            if token in report_lower and token not in found_types:
                found_types.append(token)
    missed_types = [token for token in decision_facets if token not in set(found_types)]

    submission_payload = json.dumps(
        {"selectedCommits": normalized_selected_commits, "report": normalized_report},
        ensure_ascii=False,
    )
    submission = Submission(
        user_id=user_id,
        problem_id=problem.id,
        language=problem.language,
        code=submission_payload,
        status=SubmissionStatus.passed if is_correct else SubmissionStatus.failed,
        score=int(round(score)),
    )
    db.add(submission)
    db.flush()

    analysis_detail = {
        "feedback": feedback,
        "found_types": found_types,
        "missed_types": missed_types,
        "reference_report": reference_report,
        "selected_commits": normalized_selected_commits,
        "culprit_commits": culprit_commits,
        "commit_reviews": commit_reviews,
        "pass_threshold": int(CODE_BLAME_PASS_THRESHOLD),
        "analysis_error_detail": extract_analysis_error_detail(evaluation),
        "raw_evaluation": evaluation,
    }
    analysis_detail_json = json.dumps(analysis_detail, ensure_ascii=False)

    db.add(
        AIAnalysis(
            user_id=user_id,
            submission_id=submission.id,
            analysis_type=AnalysisType.review,
            result_summary=feedback["summary"][:1000] or "code_blame_review_completed",
            result_detail=analysis_detail_json[:10000],
        )
    )

    update_user_problem_stat(
        db=db,
        user_id=user_id,
        problem_id=problem.id,
        score=submission.score,
        status=submission.status,
        analysis_summary=feedback["summary"],
        analysis_detail=analysis_detail_json,
        increment_attempt=True,
    )

    db.commit()
    from app.services.platform_public_bridge import invalidate_public_history_total_for_user_id

    invalidate_public_history_total_for_user_id(db, user_id)

    return {
        "correct": is_correct,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "foundTypes": found_types,
        "missedTypes": missed_types,
        "referenceReport": reference_report,
        "passThreshold": int(CODE_BLAME_PASS_THRESHOLD),
        "selectedCommits": normalized_selected_commits,
        "culpritCommits": culprit_commits,
        "commitReviews": commit_reviews,
    }
