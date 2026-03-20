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
    normalize_str_list as _shared_normalize_str_list,
    normalize_trap_types as _shared_normalize_trap_types,
)
from backend.mode_policies import (
    AUDITOR_TRAP_COUNT_BY_DIFFICULTY,
    CLIENT_TO_PLATFORM_DIFFICULTY,
    MODE_PASS_THRESHOLD,
)
from backend.security import generate_token

AUDITOR_PASS_THRESHOLD = MODE_PASS_THRESHOLD
AUDITOR_TRACK_ID = "algorithms"

_DIFFICULTY_TO_DB: dict[str, ProblemDifficulty] = {
    key: ProblemDifficulty(value) for key, value in CLIENT_TO_PLATFORM_DIFFICULTY.items()
}
_DIFFICULTY_TO_TRAP_COUNT = AUDITOR_TRAP_COUNT_BY_DIFFICULTY

_mode_ai = get_platform_mode_ai_bridge()
_generator = _mode_ai
_ai_client = _mode_ai


def map_auditor_difficulty(difficulty: str) -> ProblemDifficulty:
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


def _trap_count_for_difficulty(difficulty: str) -> int:
    normalized = _normalized_difficulty(difficulty)
    return _DIFFICULTY_TO_TRAP_COUNT[normalized]


def _normalize_str_list(value: Any) -> list[str]:
    return _shared_normalize_str_list(value)


def _normalize_trap_types(value: Any) -> list[str]:
    return _shared_normalize_trap_types(value)


def create_auditor_problem(
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
    mapped_difficulty = map_auditor_difficulty(normalized_difficulty)
    trap_count = _trap_count_for_difficulty(normalized_difficulty)

    generator_problem_id = generate_token("pauditor")
    try:
        generated = _generator.generate_auditor_problem_sync(
            problem_id=generator_problem_id,
            track_id=AUDITOR_TRACK_ID,
            language_id=normalized_language,
            difficulty=normalized_difficulty,
            mode="auditor",
            trap_count=trap_count,
            history_context=None,
        )
    except Exception as exc:
        raise ValueError("문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    trap_catalog = generated.get("trap_catalog") if isinstance(generated.get("trap_catalog"), list) else []
    reference_report = str(generated.get("reference_report") or "").strip()
    prompt = str(generated.get("prompt") or "").strip() or "코드의 치명적 함정을 찾아 감사 리포트를 작성하세요."
    title = str(generated.get("title") or "").strip() or "감사관 코드 리뷰 문제"
    code = str(generated.get("code") or "").strip()

    problem = Problem(
        kind=ProblemKind.auditor,
        title=title,
        description=prompt,
        difficulty=mapped_difficulty,
        language=normalized_language,
        starter_code=code,
        options={
            "trap_catalog": trap_catalog,
            "reference_report": reference_report,
            "trap_count": trap_count,
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
        "code": code,
        "prompt": prompt,
        "trapCount": len(trap_catalog) if trap_catalog else trap_count,
    }


def _resolve_auditor_problem(db: Session, *, user_id: int, problem_id: str) -> Problem:
    normalized_problem_id = str(problem_id or "").strip()
    if not normalized_problem_id:
        raise ValueError("problemId가 올바르지 않습니다.")

    problem: Problem | None = None
    try:
        problem = db.get(Problem, int(normalized_problem_id))
    except (TypeError, ValueError):
        problem = None

    if problem is None:
        query = getattr(db, "query", None)
        if callable(query):
            problem = query(Problem).filter(Problem.external_id == normalized_problem_id).first()

    if not problem or problem.kind != ProblemKind.auditor:
        raise ValueError("problemId가 올바르지 않습니다.")
    if problem.created_by is not None and int(problem.created_by) != int(user_id):
        raise ValueError("problemId가 올바르지 않습니다.")
    return problem


def submit_auditor_report(
    db: Session,
    *,
    user_id: int,
    problem_id: str,
    report: str,
) -> dict[str, Any]:
    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("report must not be empty")
    if len(normalized_report) > 12000:
        raise ValueError("report must be <= 12000 chars")

    problem = _resolve_auditor_problem(db, user_id=user_id, problem_id=problem_id)

    options = problem.options if isinstance(problem.options, dict) else {}
    trap_catalog = options.get("trap_catalog") if isinstance(options.get("trap_catalog"), list) else []
    reference_report = str(
        options.get("reference_report")
        or problem.reference_solution
        or ""
    ).strip()
    difficulty_for_ai = str(options.get("client_difficulty") or "intermediate")

    expected_trap_types = _normalize_trap_types(trap_catalog)
    try:
        evaluation = _ai_client.analyze_auditor_report(
            code=str(problem.starter_code or ""),
            prompt=str(problem.description or ""),
            report=normalized_report,
            trap_catalog=trap_catalog,
            reference_report=reference_report,
            language=str(problem.language or ""),
            difficulty=difficulty_for_ai,
        )
    except Exception as exc:
        evaluation = build_ai_evaluation_fallback(
            missed_types=expected_trap_types,
            error=exc,
        )

    score_raw = evaluation.get("score")
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))
    verdict = "passed" if score >= AUDITOR_PASS_THRESHOLD else "failed"
    is_correct = verdict == "passed"

    feedback = {
        "summary": str(evaluation.get("summary") or ""),
        "strengths": _normalize_str_list(evaluation.get("strengths")),
        "improvements": _normalize_str_list(evaluation.get("improvements")),
    }
    found_types = _normalize_str_list(evaluation.get("found_types"))
    missed_types = _normalize_str_list(evaluation.get("missed_types"))

    submission = Submission(
        user_id=user_id,
        problem_id=problem.id,
        language=problem.language,
        code=normalized_report,
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
        "pass_threshold": int(AUDITOR_PASS_THRESHOLD),
        "analysis_error_detail": extract_analysis_error_detail(evaluation),
        "raw_evaluation": evaluation,
    }
    analysis_detail_json = json.dumps(analysis_detail, ensure_ascii=False)

    db.add(
        AIAnalysis(
            user_id=user_id,
            submission_id=submission.id,
            analysis_type=AnalysisType.review,
            result_summary=feedback["summary"][:1000] or "auditor_review_completed",
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
        "passThreshold": int(AUDITOR_PASS_THRESHOLD),
    }
