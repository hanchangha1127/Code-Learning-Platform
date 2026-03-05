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
    select_context_inference_type as _shared_select_context_inference_type,
)
from backend.mode_policies import (
    CLIENT_TO_PLATFORM_DIFFICULTY,
    CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
    CONTEXT_INFERENCE_TYPE_WEIGHTS,
    MODE_PASS_THRESHOLD,
)
from backend.security import generate_token

CONTEXT_INFERENCE_PASS_THRESHOLD = MODE_PASS_THRESHOLD
CONTEXT_INFERENCE_TRACK_ID = "algorithms"

_DIFFICULTY_TO_DB: dict[str, ProblemDifficulty] = {
    key: ProblemDifficulty(value) for key, value in CLIENT_TO_PLATFORM_DIFFICULTY.items()
}

_mode_ai = get_platform_mode_ai_bridge()
_generator = _mode_ai
_ai_client = _mode_ai


def map_context_inference_difficulty(difficulty: str) -> ProblemDifficulty:
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


def select_context_inference_type(difficulty: str) -> str:
    normalized = _normalized_difficulty(difficulty)
    return _shared_select_context_inference_type(
        normalized,
        weights_by_difficulty=CONTEXT_INFERENCE_TYPE_WEIGHTS,
        default_difficulty=None,
    )


def _complexity_profile_for_difficulty(difficulty: str) -> str:
    normalized = _normalized_difficulty(difficulty)
    return CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY[normalized]


def _normalize_str_list(value: Any) -> list[str]:
    return _shared_normalize_str_list(value)


def create_context_inference_problem(
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
    mapped_difficulty = map_context_inference_difficulty(normalized_difficulty)
    inference_type = select_context_inference_type(normalized_difficulty)
    complexity_profile = _complexity_profile_for_difficulty(normalized_difficulty)

    generator_problem_id = generate_token("pctx")
    try:
        generated = _generator.generate_context_inference_problem_sync(
            problem_id=generator_problem_id,
            track_id=CONTEXT_INFERENCE_TRACK_ID,
            language_id=normalized_language,
            difficulty=normalized_difficulty,
            mode="context-inference",
            inference_type=inference_type,
            complexity_profile=complexity_profile,
            history_context=None,
        )
    except Exception as exc:
        raise ValueError("문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    expected_facets = _normalize_str_list(generated.get("expected_facets"))
    reference_report = str(generated.get("reference_report") or "").strip()
    resolved_type = str(generated.get("inference_type") or inference_type).strip().lower()
    if resolved_type not in {"pre_condition", "post_condition"}:
        resolved_type = inference_type

    snippet = str(generated.get("snippet") or "").rstrip()
    prompt = str(generated.get("prompt") or "").strip() or "코드 맥락을 추론해 리포트를 작성하세요."
    title = str(generated.get("title") or "").strip() or "맥락 추론 문제"

    problem = Problem(
        kind=ProblemKind.context_inference,
        title=title,
        description=prompt,
        difficulty=mapped_difficulty,
        language=normalized_language,
        starter_code=snippet,
        options={
            "expected_facets": expected_facets,
            "reference_report": reference_report,
            "inference_type": resolved_type,
            "complexity_profile": complexity_profile,
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
        "snippet": snippet,
        "prompt": prompt,
        "inferenceType": resolved_type,
    }


def submit_context_inference_report(
    db: Session,
    *,
    user_id: int,
    problem_id: str,
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
    if not problem or problem.kind != ProblemKind.context_inference:
        raise ValueError("problemId is invalid")
    if problem.created_by is not None and int(problem.created_by) != int(user_id):
        raise ValueError("problemId is invalid")

    options = problem.options if isinstance(problem.options, dict) else {}
    expected_facets = _normalize_str_list(options.get("expected_facets"))
    reference_report = str(options.get("reference_report") or problem.reference_solution or "").strip()
    inference_type = str(options.get("inference_type") or "pre_condition").strip().lower()
    if inference_type not in {"pre_condition", "post_condition"}:
        inference_type = "pre_condition"
    difficulty_for_ai = str(options.get("client_difficulty") or "intermediate")

    try:
        evaluation = _ai_client.analyze_context_inference_report(
            snippet=str(problem.starter_code or ""),
            prompt=str(problem.description or ""),
            report=normalized_report,
            expected_facets=expected_facets,
            reference_report=reference_report,
            inference_type=inference_type,
            language=str(problem.language or ""),
            difficulty=difficulty_for_ai,
        )
    except Exception as exc:
        evaluation = build_ai_evaluation_fallback(
            missed_types=expected_facets,
            error=exc,
        )

    score_raw = evaluation.get("score")
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))
    verdict = "passed" if score >= CONTEXT_INFERENCE_PASS_THRESHOLD else "failed"
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
        "inference_type": inference_type,
        "pass_threshold": int(CONTEXT_INFERENCE_PASS_THRESHOLD),
        "analysis_error_detail": extract_analysis_error_detail(evaluation),
        "raw_evaluation": evaluation,
    }
    analysis_detail_json = json.dumps(analysis_detail, ensure_ascii=False)

    db.add(
        AIAnalysis(
            user_id=user_id,
            submission_id=submission.id,
            analysis_type=AnalysisType.review,
            result_summary=feedback["summary"][:1000] or "context_inference_review_completed",
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

    return {
        "correct": is_correct,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "foundTypes": found_types,
        "missedTypes": missed_types,
        "referenceReport": reference_report,
        "passThreshold": int(CONTEXT_INFERENCE_PASS_THRESHOLD),
    }
