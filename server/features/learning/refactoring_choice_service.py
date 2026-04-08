from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.db.models import (
    AIAnalysis,
    AnalysisType,
    Problem,
    ProblemDifficulty,
    ProblemKind,
    Submission,
    SubmissionStatus,
)
from server.features.learning.ai_providers.platform_mode_bridge import get_platform_mode_ai_bridge
from server.features.learning.problem_stat_service import update_user_problem_stat
from server.infra.ai_fallback import build_ai_evaluation_fallback, extract_analysis_error_detail
from server.features.learning.normalization import (
    normalize_facets,
    normalize_option_id,
    normalize_refactoring_choice_option_reviews,
    normalize_refactoring_choice_options,
    normalize_str_list,
)
from server.features.learning.policies import (
    CLIENT_TO_PLATFORM_DIFFICULTY,
    MODE_PASS_THRESHOLD,
    REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
    REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY,
    REFACTORING_CHOICE_FACET_TAXONOMY,
    REFACTORING_CHOICE_OPTION_IDS,
)
from server.infra.security import generate_token

REFACTORING_CHOICE_PASS_THRESHOLD = MODE_PASS_THRESHOLD
REFACTORING_CHOICE_TRACK_ID = "algorithms"

_DIFFICULTY_TO_DB: dict[str, ProblemDifficulty] = {
    key: ProblemDifficulty(value) for key, value in CLIENT_TO_PLATFORM_DIFFICULTY.items()
}

_mode_ai = get_platform_mode_ai_bridge()
_generator = _mode_ai
_ai_client = _mode_ai


def map_refactoring_choice_difficulty(difficulty: str) -> ProblemDifficulty:
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


def _constraint_count_for_difficulty(difficulty: str) -> int:
    normalized = _normalized_difficulty(difficulty)
    return REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY[normalized]


def _complexity_profile_for_difficulty(difficulty: str) -> str:
    normalized = _normalized_difficulty(difficulty)
    return REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY[normalized]


def create_refactoring_choice_problem(
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
    mapped_difficulty = map_refactoring_choice_difficulty(normalized_difficulty)
    constraint_count = _constraint_count_for_difficulty(normalized_difficulty)
    complexity_profile = _complexity_profile_for_difficulty(normalized_difficulty)

    generator_problem_id = generate_token("prefactor")
    try:
        generated = _generator.generate_refactoring_choice_problem_sync(
            problem_id=generator_problem_id,
            track_id=REFACTORING_CHOICE_TRACK_ID,
            language_id=normalized_language,
            difficulty=normalized_difficulty,
            mode="refactoring-choice",
            complexity_profile=complexity_profile,
            constraint_count=constraint_count,
            history_context=None,
        )
    except Exception as exc:
        raise ValueError("문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    title = str(generated.get("title") or "").strip() or "Refactoring Choice Problem"
    scenario = str(generated.get("scenario") or "").strip()
    prompt = str(generated.get("prompt") or "").strip() or "Choose the best option among A/B/C and explain your reasoning."

    constraints = normalize_str_list(generated.get("constraints"))
    if len(constraints) > constraint_count:
        constraints = constraints[:constraint_count]
    while len(constraints) < constraint_count:
        constraints.append(f"Constraint {len(constraints) + 1}")

    options = normalize_refactoring_choice_options(
        generated.get("options"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_title_template="{option_id} option",
        missing_code="def solution():\n    pass",
    )
    decision_facets = normalize_facets(
        generated.get("decision_facets"),
        taxonomy=REFACTORING_CHOICE_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )
    best_option = normalize_option_id(
        generated.get("best_option"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        fallback_option_id="A",
    )
    option_reviews = normalize_refactoring_choice_option_reviews(
        generated.get("option_reviews"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_summary_template="{option_id} option summary is unavailable.",
    )
    reference_report = str(generated.get("reference_report") or "").strip()
    if not reference_report:
        reference_report = (
            f"Recommended option is {best_option}. "
            "Explain your decision by comparing trade-offs across constraints and key facets."
        )

    problem = Problem(
        kind=ProblemKind.refactoring_choice,
        title=title,
        description=prompt,
        difficulty=mapped_difficulty,
        language=normalized_language,
        starter_code=scenario,
        options={
            "scenario": scenario,
            "constraints": constraints,
            "options": options,
            "decision_facets": decision_facets,
            "best_option": best_option,
            "reference_report": reference_report,
            "option_reviews": option_reviews,
            "client_difficulty": normalized_difficulty,
            "complexity_profile": complexity_profile,
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
        "scenario": scenario,
        "constraints": constraints,
        "options": options,
        "prompt": prompt,
        "decisionFacets": decision_facets,
    }


def submit_refactoring_choice_report(
    db: Session,
    *,
    user_id: int,
    problem_id: str,
    selected_option: str,
    report: str,
) -> dict[str, Any]:
    try:
        parsed_problem_id = int(str(problem_id).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("problemId is invalid") from exc

    normalized_selected_option = str(selected_option or "").strip().upper()
    if normalized_selected_option not in REFACTORING_CHOICE_OPTION_IDS:
        raise ValueError("selectedOption must be one of A, B, C")

    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("report must not be empty")
    if len(normalized_report) > 12000:
        raise ValueError("report must be <= 12000 chars")

    problem = db.get(Problem, parsed_problem_id)
    if not problem or problem.kind != ProblemKind.refactoring_choice:
        raise ValueError("problemId is invalid")
    if problem.created_by is not None and int(problem.created_by) != int(user_id):
        raise ValueError("problemId is invalid")

    options_json = problem.options if isinstance(problem.options, dict) else {}
    scenario = str(options_json.get("scenario") or problem.starter_code or "").strip()
    constraints = normalize_str_list(options_json.get("constraints"))
    choice_options = normalize_refactoring_choice_options(
        options_json.get("options"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_title_template="{option_id} option",
        missing_code="def solution():\n    pass",
    )
    decision_facets = normalize_facets(
        options_json.get("decision_facets"),
        taxonomy=REFACTORING_CHOICE_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )
    best_option = normalize_option_id(
        options_json.get("best_option"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        fallback_option_id="A",
    )
    reference_report = str(options_json.get("reference_report") or problem.reference_solution or "").strip()
    option_reviews = normalize_refactoring_choice_option_reviews(
        options_json.get("option_reviews"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_summary_template="{option_id} option summary is unavailable.",
    )
    difficulty_for_ai = str(options_json.get("client_difficulty") or "intermediate")

    try:
        evaluation = _ai_client.analyze_refactoring_choice_report(
            scenario=scenario,
            prompt=str(problem.description or ""),
            constraints=constraints,
            options=choice_options,
            selected_option=normalized_selected_option,
            best_option=best_option,
            report=normalized_report,
            decision_facets=decision_facets,
            reference_report=reference_report,
            option_reviews=option_reviews,
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
    verdict = "passed" if score >= REFACTORING_CHOICE_PASS_THRESHOLD else "failed"
    is_correct = verdict == "passed"

    feedback = {
        "summary": str(evaluation.get("summary") or ""),
        "strengths": normalize_str_list(evaluation.get("strengths")),
        "improvements": normalize_str_list(evaluation.get("improvements")),
    }
    expected_set = set(decision_facets)
    found_types: list[str] = []
    for token in normalize_str_list(evaluation.get("found_types")):
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
        {"selectedOption": normalized_selected_option, "report": normalized_report},
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
        "selected_option": normalized_selected_option,
        "best_option": best_option,
        "option_reviews": option_reviews,
        "pass_threshold": int(REFACTORING_CHOICE_PASS_THRESHOLD),
        "analysis_error_detail": extract_analysis_error_detail(evaluation),
        "raw_evaluation": evaluation,
    }
    analysis_detail_json = json.dumps(analysis_detail, ensure_ascii=False)

    db.add(
        AIAnalysis(
            user_id=user_id,
            submission_id=submission.id,
            analysis_type=AnalysisType.review,
            result_summary=feedback["summary"][:1000] or "refactoring_choice_review_completed",
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
    from server.features.learning.history import invalidate_public_history_total_for_user_id

    invalidate_public_history_total_for_user_id(db, user_id)

    return {
        "correct": is_correct,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "foundTypes": found_types,
        "missedTypes": missed_types,
        "referenceReport": reference_report,
        "passThreshold": int(REFACTORING_CHOICE_PASS_THRESHOLD),
        "selectedOption": normalized_selected_option,
        "bestOption": best_option,
        "optionReviews": option_reviews,
    }

