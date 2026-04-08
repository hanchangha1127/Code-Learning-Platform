"""Domain services orchestrating storage, diagnostics, and learning logic."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import random
from typing import Any, Callable, Dict, List, Optional

from server.infra.ai_client import AIClient
from server.features.learning import reporting as learning_reporting
from server.features.learning import tiering as learning_tier
from server.features.learning.content import LANGUAGES, TRACKS, normalize_language_id
from server.features.learning.normalization import (
    normalize_code_blame_commit_reviews,
    normalize_code_blame_commits,
    normalize_code_blame_facets,
    normalize_code_blame_option_ids,
    normalize_facets,
    normalize_refactoring_choice_option_reviews,
    normalize_refactoring_choice_options,
    normalize_str_list,
    select_context_inference_type,
    select_weighted_count,
)
from server.features.learning.policies import (
    AUDITOR_TRAP_COUNT_BY_DIFFICULTY,
    CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY,
    CODE_BLAME_CULPRIT_COUNT_WEIGHTS,
    CODE_BLAME_FACET_TAXONOMY,
    CODE_BLAME_OPTION_IDS,
    CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
    CONTEXT_INFERENCE_TYPE_WEIGHTS,
    MODE_PASS_THRESHOLD,
    REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
    REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY,
    REFACTORING_CHOICE_FACET_TAXONOMY,
    REFACTORING_CHOICE_OPTION_IDS,
)
from server.features.learning.generator import ProblemGenerator
from server.infra.security import generate_token
from server.features.learning.skill_levels import DEFAULT_SKILL_LEVEL, normalize_skill_level, score_to_skill_level
from server.infra.user_storage import UserStorageManager
from server.infra.user_service import UserService

DEFAULT_DIAGNOSTIC_TOTAL = 5
DEFAULT_TRACK_ID = "algorithms"
TIER_REVIEW_WINDOW = 10
TIER_ADVANCED_THRESHOLD = 0.8
TIER_INTERMEDIATE_THRESHOLD = 0.6
TIER_BEGINNER_RATIO_LIMIT = 0.7

DIFFICULTY_CHOICES: Dict[str, Dict[str, str]] = {
    "beginner": {"title": "초급", "generator": "beginner"},
    "intermediate": {"title": "중급", "generator": "intermediate"},
    "advanced": {"title": "고급", "generator": "advanced"},
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_requested_language(language_id: str) -> str:
    normalized = normalize_language_id(language_id)
    if normalized is None:
        raise ValueError("지원하지 않는 언어입니다.")
    return normalized


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    start_dt = _parse_iso(start)
    end_dt = _parse_iso(end)
    if not start_dt or not end_dt:
        return None
    delta = end_dt - start_dt
    seconds = delta.total_seconds()
    return seconds if seconds >= 0 else None


def _accuracy_from_events(events: list[dict]) -> float | None:
    attempts = len(events)
    if attempts == 0:
        return None
    correct = sum(1 for event in events if event.get("correct") is True)
    return round((correct / attempts) * 100, 1)


def _lighten_hint(text: str) -> str:
    """Trim and shorten a hint for display."""

    stripped = (text or "").strip()
    if len(stripped) > 280:
        return stripped[:277] + "..."
    return stripped


def _default_profile(username: str) -> Dict[str, Any]:
    now = _utcnow()
    return {
        "type": "profile",
        "username": username,
        "skill_level": DEFAULT_SKILL_LEVEL,
        "diagnostic_completed": True,
        "diagnostic_total": 0,
        "diagnostic_given": 0,
        "diagnostic_results": [],
        "pending_problems": [],
        "stats": {"attempts": 0, "correct": 0},
        "created_at": now,
        "updated_at": now,
    }




# Mode handlers --------------------------------------------------------

AUDITOR_PASS_THRESHOLD = MODE_PASS_THRESHOLD

CONTEXT_INFERENCE_PASS_THRESHOLD = MODE_PASS_THRESHOLD

REFACTORING_CHOICE_PASS_THRESHOLD = MODE_PASS_THRESHOLD

CODE_BLAME_PASS_THRESHOLD = MODE_PASS_THRESHOLD

ADVANCED_ANALYSIS_PASS_THRESHOLD = MODE_PASS_THRESHOLD


def _slug_token(value: object, fallback: str) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return cleaned or fallback


def _normalize_advanced_analysis_files(
    value: object,
    *,
    min_count: int,
    max_count: int,
    default_language: str,
    default_role: str,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if isinstance(value, list):
        for index, entry in enumerate(value, start=1):
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or entry.get("name") or "").strip()
            name = str(entry.get("name") or "").strip()
            if not path and name:
                path = name
            if not name and path:
                name = path.split("/")[-1]
            if not path:
                path = f"src/file_{index}.txt"
            if not name:
                name = path.split("/")[-1]
            language = str(entry.get("language") or default_language).strip().lower() or default_language
            role = str(entry.get("role") or default_role).strip() or default_role
            content = str(entry.get("content") or entry.get("code") or "").rstrip()
            if not content:
                continue
            normalized.append(
                {
                    "id": str(entry.get("id") or _slug_token(path, f"file-{index}")),
                    "path": path,
                    "name": name,
                    "language": language,
                    "role": role,
                    "content": content,
                }
            )
    return normalized[: max(1, int(max_count or 1))]


def _normalize_report_text(report: str) -> str:
    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("리포트를 입력해주세요.")
    if len(normalized_report) > 12000:
        raise ValueError("리포트 길이는 12000자를 초과할 수 없습니다.")
    return normalized_report


def _load_mode_instance(storage: Any, *, instance_type: str, problem_id: str, missing_message: str) -> dict[str, Any]:
    instance = storage.find_one(
        lambda item: item.get("type") == instance_type and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError(missing_message)
    return instance


def _fallback_report_evaluation(exc: Exception, *, missed_types: list[str] | None = None) -> dict[str, Any]:
    evaluation = {
        "summary": "AI 채점 중 오류가 발생해 기본 실패 응답을 반환했습니다. 잠시 후 다시 시도해주세요.",
        "strengths": [],
        "improvements": ["리포트 내용을 유지한 채 재시도해주세요."],
        "score": 0.0,
        "correct": False,
        "error_detail": str(exc),
    }
    if missed_types is not None:
        evaluation["found_types"] = []
        evaluation["missed_types"] = missed_types
    return evaluation


def _clamp_score(score: object) -> float:
    try:
        value = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(100.0, value))


def _score_verdict(evaluation: dict[str, Any] | None, *, threshold: float) -> tuple[float, bool, str]:
    score = _clamp_score(evaluation.get("score") if isinstance(evaluation, dict) else 0.0)
    is_passed = score >= threshold
    return score, is_passed, "passed" if is_passed else "failed"


def _evaluation_feedback(evaluation: dict[str, Any] | None) -> dict[str, Any]:
    source = evaluation or {}
    return {
        "summary": str(source.get("summary") or ""),
        "strengths": normalize_str_list(source.get("strengths")),
        "improvements": normalize_str_list(source.get("improvements")),
    }


def _evaluation_metadata(evaluation: dict[str, Any] | None) -> tuple[str, str | None, str]:
    source = evaluation or {}
    feedback_source = str(source.get("feedback_source") or "fallback")
    ai_provider = str(source.get("ai_provider") or "").strip() or None
    analysis_error_detail = str(source.get("error_detail") or "")
    return feedback_source, ai_provider, analysis_error_detail


def _resolve_decision_type_results(
    evaluation: dict[str, Any] | None,
    *,
    expected_types: list[str],
    report: str,
) -> tuple[list[str], list[str]]:
    expected_set = set(expected_types)
    found_types: list[str] = []
    for token in normalize_str_list((evaluation or {}).get("found_types")):
        lowered = token.lower()
        if lowered not in expected_set or lowered in found_types:
            continue
        found_types.append(lowered)
    if not found_types and expected_types:
        report_lower = report.lower()
        for token in expected_types:
            if token in report_lower and token not in found_types:
                found_types.append(token)
    missed_types = [token for token in expected_types if token not in set(found_types)]
    return found_types, missed_types


def _request_advanced_analysis_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]],
    token_prefix: str,
    generator_method_name: str,
    history_loader_name: str,
    instance_type: str,
    mode: str,
    title_fallback: str,
    workspace_fallback: str,
    min_files: int,
    max_files: int,
    default_role: str,
    checklist_limit: int,
) -> Dict[str, Any]:
    track_id = default_track_id
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다.")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    history_context = getattr(service, history_loader_name)(storage)
    problem_id = generate_token(token_prefix)
    generated = getattr(service.problem_generator, generator_method_name)(
        problem_id=problem_id,
        track_id=track_id,
        language_id=language_id,
        difficulty=difficulty_choices[difficulty_id]["generator"],
        mode=mode,
        history_context=history_context,
        on_text_delta=on_text_delta,
    )

    files = _normalize_advanced_analysis_files(
        generated.get("files"),
        min_count=min_files,
        max_count=max_files,
        default_language=language_id,
        default_role=default_role,
    )
    checklist = normalize_str_list(generated.get("checklist"))[:checklist_limit]
    summary = str(generated.get("summary") or "").strip()
    prompt = str(generated.get("prompt") or "").strip()
    workspace = str(generated.get("workspace") or "").strip() or workspace_fallback
    reference_report = str(generated.get("reference_report") or "").strip()
    title = generated.get("title") or title_fallback

    storage.append(
        {
            "type": instance_type,
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": mode,
            "difficulty": difficulty_id,
            "title": title,
            "summary": summary,
            "prompt": prompt,
            "workspace": workspace,
            "checklist": checklist,
            "files": files,
            "reference_report": reference_report,
            "created_at": utcnow(),
        }
    )

    return {
        "problemId": problem_id,
        "title": title,
        "mode": mode,
        "summary": summary,
        "language": language_id,
        "difficulty": difficulty_id,
        "workspace": workspace,
        "files": files,
        "prompt": prompt,
        "checklist": checklist,
    }


def _submit_report_mode(
    service: Any,
    username: str,
    storage: Any,
    instance: dict[str, Any],
    problem_id: str,
    normalized_report: str,
    evaluation: dict[str, Any] | None,
    *,
    event_type: str,
    mode: str,
    pass_threshold: float,
    reference_report: str,
    utcnow: Callable[[], str],
    found_types: list[str] | None = None,
    missed_types: list[str] | None = None,
    event_extra: dict[str, Any] | None = None,
    response_extra: dict[str, Any] | None = None,
    include_analysis_error_detail: bool = True,
) -> Dict[str, Any]:
    score, is_passed, verdict = _score_verdict(evaluation, threshold=pass_threshold)
    feedback = _evaluation_feedback(evaluation)
    feedback_source, ai_provider, analysis_error_detail = _evaluation_metadata(evaluation)

    event_payload = {
        "type": event_type,
        "problem_id": problem_id,
        "track": instance.get("track"),
        "language": instance.get("language"),
        "mode": mode,
        "difficulty": instance.get("difficulty"),
        "report": normalized_report,
        "score": score,
        "correct": is_passed,
        "verdict": verdict,
        "feedback": feedback,
        "feedback_source": feedback_source,
        "ai_provider": ai_provider,
        "reference_report": reference_report,
        "pass_threshold": pass_threshold,
        "created_at": utcnow(),
    }
    if found_types is not None:
        event_payload["found_types"] = found_types
    if missed_types is not None:
        event_payload["missed_types"] = missed_types
    if include_analysis_error_detail:
        event_payload["analysis_error_detail"] = analysis_error_detail
    if event_extra:
        event_payload.update(event_extra)

    storage.append(event_payload)
    service._update_tier_if_needed(storage, username)

    response = {
        "correct": is_passed,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "feedbackSource": feedback_source,
        "aiProvider": ai_provider,
        "referenceReport": reference_report,
        "passThreshold": int(pass_threshold),
    }
    if found_types is not None:
        response["foundTypes"] = found_types
    if missed_types is not None:
        response["missedTypes"] = missed_types
    if response_extra:
        response.update(response_extra)
    return response


def _record_mode_event(
    service: Any,
    storage: Any,
    username: str,
    *,
    event_type: str,
    problem_id: str,
    instance: dict[str, Any],
    utcnow: Callable[[], str],
    event_extra: dict[str, Any],
) -> None:
    event_payload = {
        "type": event_type,
        "problem_id": problem_id,
        "language": instance.get("language"),
        "difficulty": instance.get("difficulty"),
        "created_at": utcnow(),
    }
    track = instance.get("track")
    if track is not None:
        event_payload["track"] = track
    event_payload.update(event_extra)
    storage.append(event_payload)
    service._update_tier_if_needed(storage, username)


def request_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    track_id = default_track_id
    if track_id not in TRACKS:
        raise ValueError("학습 트랙을 찾을 수 없습니다.")
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다.")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    profile = service._ensure_profile(storage, username)
    profile = service._ensure_practice_ready(storage, username, profile)

    difficulty_meta = difficulty_choices[difficulty_id]
    generator_difficulty = difficulty_meta["generator"]
    mode = "practice"

    problem_id = generate_token("problem")
    history_context = service._problem_history_context(storage)

    retry_context = None
    last_event = service._get_last_learning_event(storage)
    if last_event and last_event.get("correct") is False:
        failed_problem_id = last_event.get("problem_id")
        failed_instance = service._get_problem_instance(storage, failed_problem_id)
        if failed_instance:
            retry_context = {
                "title": failed_instance.get("title", ""),
                "code": failed_instance.get("code", ""),
                "prompt": failed_instance.get("prompt", ""),
            }

    generated = service.problem_generator.generate_sync(
        problem_id,
        track_id,
        language_id,
        generator_difficulty,
        mode,
        history_context=history_context,
        retry_context=retry_context,
        on_text_delta=on_text_delta,
    )

    storage.append(
        {
            "type": "problem_instance",
            "problem_id": generated.problem_id,
            "track": track_id,
            "language": language_id,
            "mode": generated.mode,
            "difficulty": generated.difficulty,
            "title": generated.title,
            "code": generated.code,
            "prompt": generated.prompt,
            "reference": generated.reference,
            "created_at": utcnow(),
        }
    )

    profile = service._update_profile(
        storage,
        username,
        lambda data: service._profile_after_assignment(data, generated.problem_id, False),
    )

    return {
        "problem": {
            "id": generated.problem_id,
            "title": generated.title,
            "code": generated.code,
            "prompt": generated.prompt,
            "mode": generated.mode,
            "difficulty": generated.difficulty,
            "track": track_id,
            "language": language_id,
        },
        "mode": generated.mode,
        "skillLevel": normalize_skill_level(profile.get("skill_level"), DEFAULT_SKILL_LEVEL),
        "selectedDifficulty": difficulty_meta["title"],
    }


def request_code_block_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    track_id = default_track_id
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    history_context = service._code_block_history_context(storage)

    difficulty_meta = difficulty_choices[difficulty_id]
    generator_difficulty = difficulty_meta["generator"]
    mode = "code-block"
    problem_id = generate_token("cblock")

    generated = service.problem_generator.generate_code_block_problem_sync(
        problem_id,
        track_id,
        language_id,
        generator_difficulty,
        mode,
        history_context=history_context,
        on_text_delta=on_text_delta,
    )

    storage.append(
        {
            "type": "code_block_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": mode,
            "difficulty": difficulty_id,
            "title": generated["title"],
            "objective": generated.get("objective"),
            "code": generated["code"],
            "options": generated["options"],
            "answer_index": generated["answer_index"],
            "explanation": generated["explanation"],
            "created_at": utcnow(),
        }
    )

    return {
        "problemId": problem_id,
        "title": generated["title"],
        "objective": generated.get("objective"),
        "code": generated["code"],
        "options": generated["options"],
        "difficulty": difficulty_id,
        "language": language_id,
    }


def submit_code_block_answer(
    service: Any,
    username: str,
    problem_id: str,
    selected_option: int,
    *,
    default_track_id: str,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    storage = service._get_user_storage(username)
    profile = service._ensure_profile(storage, username)
    profile = service._ensure_practice_ready(storage, username, profile)

    instance = storage.find_one(
        lambda item: item.get("type") == "code_block_instance" and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError("해당 코드 블록 문제를 찾지 못했습니다.")

    correct_answer_index = instance.get("answer_index")
    is_correct = selected_option == correct_answer_index

    _record_mode_event(
        service,
        storage,
        username,
        event_type="learning_event",
        problem_id=problem_id,
        instance={**instance, "track": instance.get("track", default_track_id)},
        utcnow=utcnow,
        event_extra={
            "mode": "code-block",
            "selected_option": selected_option,
            "correct_answer_index": correct_answer_index,
            "correct": is_correct,
        },
    )

    return {
        "correct": is_correct,
        "correctAnswer": correct_answer_index,
        "explanation": instance.get("explanation"),
        "skillLevel": normalize_skill_level(profile.get("skill_level"), DEFAULT_SKILL_LEVEL),
    }


def request_code_error_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    track_id = default_track_id
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다.")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    history_context = service._code_error_history_context(storage)
    problem_id = generate_token("cerr")

    generated = service.problem_generator.generate_code_error_problem_sync(
        problem_id=problem_id,
        track_id=track_id,
        language_id=language_id,
        difficulty=difficulty_choices[difficulty_id]["generator"],
        mode="code-error",
        history_context=history_context,
    )

    storage.append(
        {
            "type": "code_error_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "difficulty": difficulty_id,
            "title": generated["title"],
            "blocks": generated["blocks"],
            "wrong_block_index": generated["wrong_block_index"],
            "explanation": generated["explanation"],
            "created_at": utcnow(),
        }
    )

    return {
        "problemId": problem_id,
        "title": generated["title"],
        "language": language_id,
        "blocks": generated["blocks"],
    }


def submit_code_error_answer(
    service: Any,
    username: str,
    problem_id: str,
    selected_index: int,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    storage = service._get_user_storage(username)
    instance = storage.find_one(
        lambda item: item.get("type") == "code_error_instance" and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError("해당 코드 오류 문제를 찾지 못했습니다.")

    try:
        selected_idx = int(selected_index)
    except (TypeError, ValueError) as exc:
        raise ValueError("선택한 블록 번호가 올바르지 않습니다.") from exc

    correct_idx = int(instance.get("wrong_block_index", 0))
    is_correct = selected_idx == correct_idx

    _record_mode_event(
        service,
        storage,
        username,
        event_type="code_error_event",
        problem_id=problem_id,
        instance=instance,
        utcnow=utcnow,
        event_extra={
            "selected_index": selected_idx,
            "correct_index": correct_idx,
            "correct": is_correct,
        },
    )

    return {
        "correct": is_correct,
        "correctIndex": correct_idx,
        "explanation": instance.get("explanation"),
    }


def request_auditor_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    track_id = default_track_id
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다.")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    history_context = service._auditor_history_context(storage)
    trap_count = AUDITOR_TRAP_COUNT_BY_DIFFICULTY[difficulty_id]
    problem_id = generate_token("auditor")

    generated = service.problem_generator.generate_auditor_problem_sync(
        problem_id=problem_id,
        track_id=track_id,
        language_id=language_id,
        difficulty=difficulty_choices[difficulty_id]["generator"],
        mode="auditor",
        trap_count=trap_count,
        history_context=history_context,
        on_text_delta=on_text_delta,
    )

    trap_catalog = generated.get("trap_catalog") or []
    if not isinstance(trap_catalog, list):
        trap_catalog = []

    storage.append(
        {
            "type": "auditor_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": "auditor",
            "difficulty": difficulty_id,
            "title": generated.get("title"),
            "code": generated.get("code"),
            "prompt": generated.get("prompt"),
            "trap_count": trap_count,
            "trap_catalog": trap_catalog,
            "reference_report": generated.get("reference_report"),
            "created_at": utcnow(),
        }
    )

    return {
        "problemId": problem_id,
        "title": generated.get("title"),
        "language": language_id,
        "difficulty": difficulty_id,
        "code": generated.get("code"),
        "prompt": generated.get("prompt"),
        "trapCount": len(trap_catalog) if trap_catalog else trap_count,
    }


def submit_auditor_report(
    service: Any,
    username: str,
    problem_id: str,
    report: str,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    normalized_report = _normalize_report_text(report)

    storage = service._get_user_storage(username)
    instance = _load_mode_instance(
        storage,
        instance_type="auditor_instance",
        problem_id=problem_id,
        missing_message="해당 감사관 문제를 찾지 못했습니다.",
    )

    evaluation = service.ai_client.analyze_auditor_report(
        code=str(instance.get("code") or ""),
        prompt=str(instance.get("prompt") or ""),
        report=normalized_report,
        trap_catalog=instance.get("trap_catalog") or [],
        reference_report=str(instance.get("reference_report") or ""),
        language=str(instance.get("language") or ""),
        difficulty=str(instance.get("difficulty") or ""),
    )

    found_types = evaluation.get("found_types") if isinstance(evaluation.get("found_types"), list) else []
    missed_types = evaluation.get("missed_types") if isinstance(evaluation.get("missed_types"), list) else []
    reference_report = str(instance.get("reference_report") or "")
    return _submit_report_mode(
        service,
        username,
        storage,
        instance,
        problem_id,
        normalized_report,
        evaluation,
        event_type="auditor_event",
        mode="auditor",
        pass_threshold=AUDITOR_PASS_THRESHOLD,
        reference_report=reference_report,
        found_types=found_types,
        missed_types=missed_types,
        utcnow=utcnow,
        include_analysis_error_detail=False,
    )


def request_single_file_analysis_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    return _request_advanced_analysis_problem(
        service,
        username,
        language_id,
        difficulty_id,
        default_track_id=default_track_id,
        difficulty_choices=difficulty_choices,
        utcnow=utcnow,
        on_text_delta=on_text_delta,
        token_prefix="sfile",
        generator_method_name="generate_single_file_analysis_problem_sync",
        history_loader_name="_single_file_analysis_history_context",
        instance_type="single_file_analysis_instance",
        mode="single-file-analysis",
        title_fallback="단일 파일 분석 문제",
        workspace_fallback="single-file-analysis.workspace",
        min_files=1,
        max_files=1,
        default_role="entrypoint",
        checklist_limit=4,
    )


def request_multi_file_analysis_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    return _request_advanced_analysis_problem(
        service,
        username,
        language_id,
        difficulty_id,
        default_track_id=default_track_id,
        difficulty_choices=difficulty_choices,
        utcnow=utcnow,
        on_text_delta=on_text_delta,
        token_prefix="mfile",
        generator_method_name="generate_multi_file_analysis_problem_sync",
        history_loader_name="_multi_file_analysis_history_context",
        instance_type="multi_file_analysis_instance",
        mode="multi-file-analysis",
        title_fallback="다중 파일 분석 문제",
        workspace_fallback="multi-file-analysis.workspace",
        min_files=2,
        max_files=6,
        default_role="module",
        checklist_limit=5,
    )


def request_fullstack_analysis_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    return _request_advanced_analysis_problem(
        service,
        username,
        language_id,
        difficulty_id,
        default_track_id=default_track_id,
        difficulty_choices=difficulty_choices,
        utcnow=utcnow,
        on_text_delta=on_text_delta,
        token_prefix="fstack",
        generator_method_name="generate_fullstack_analysis_problem_sync",
        history_loader_name="_fullstack_analysis_history_context",
        instance_type="fullstack_analysis_instance",
        mode="fullstack-analysis",
        title_fallback="풀스택 코드 분석 문제",
        workspace_fallback="fullstack-analysis.workspace",
        min_files=3,
        max_files=8,
        default_role="backend",
        checklist_limit=5,
    )


def _submit_advanced_analysis_report(
    service: Any,
    username: str,
    problem_id: str,
    report: str,
    *,
    instance_type: str,
    event_type: str,
    mode: str,
    missing_problem_message: str,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    normalized_report = _normalize_report_text(report)

    storage = service._get_user_storage(username)
    instance = _load_mode_instance(
        storage,
        instance_type=instance_type,
        problem_id=problem_id,
        missing_message=missing_problem_message,
    )

    files = _normalize_advanced_analysis_files(
        instance.get("files"),
        min_count=1,
        max_count=8,
        default_language=str(instance.get("language") or "python"),
        default_role="module",
    )
    reference_report = str(instance.get("reference_report") or "").strip()
    checklist = normalize_str_list(instance.get("checklist"))[:5]
    summary = str(instance.get("summary") or "").strip()
    prompt = str(instance.get("prompt") or "").strip()

    try:
        evaluation = service.ai_client.analyze_advanced_analysis_report(
            mode=mode,
            files=files,
            prompt=prompt,
            report=normalized_report,
            reference_report=reference_report,
            language=str(instance.get("language") or ""),
            difficulty=str(instance.get("difficulty") or ""),
            summary=summary,
            checklist=checklist,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        evaluation = _fallback_report_evaluation(exc)

    return _submit_report_mode(
        service,
        username,
        storage,
        instance,
        problem_id,
        normalized_report,
        evaluation,
        event_type=event_type,
        mode=mode,
        pass_threshold=ADVANCED_ANALYSIS_PASS_THRESHOLD,
        reference_report=reference_report,
        utcnow=utcnow,
    )


def submit_single_file_analysis_report(
    service: Any,
    username: str,
    problem_id: str,
    report: str,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    return _submit_advanced_analysis_report(
        service,
        username,
        problem_id,
        report,
        instance_type="single_file_analysis_instance",
        event_type="single_file_analysis_event",
        mode="single-file-analysis",
        missing_problem_message="해당 단일 파일 분석 문제를 찾지 못했습니다.",
        utcnow=utcnow,
    )


def submit_multi_file_analysis_report(
    service: Any,
    username: str,
    problem_id: str,
    report: str,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    return _submit_advanced_analysis_report(
        service,
        username,
        problem_id,
        report,
        instance_type="multi_file_analysis_instance",
        event_type="multi_file_analysis_event",
        mode="multi-file-analysis",
        missing_problem_message="해당 다중 파일 분석 문제를 찾지 못했습니다.",
        utcnow=utcnow,
    )


def submit_fullstack_analysis_report(
    service: Any,
    username: str,
    problem_id: str,
    report: str,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    return _submit_advanced_analysis_report(
        service,
        username,
        problem_id,
        report,
        instance_type="fullstack_analysis_instance",
        event_type="fullstack_analysis_event",
        mode="fullstack-analysis",
        missing_problem_message="해당 풀스택 코드 분석 문제를 찾지 못했습니다.",
        utcnow=utcnow,
    )


def request_context_inference_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    track_id = default_track_id
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다.")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    history_context = service._context_inference_history_context(storage)
    inference_type = select_context_inference_type(
        difficulty_id,
        weights_by_difficulty=CONTEXT_INFERENCE_TYPE_WEIGHTS,
        default_difficulty="intermediate",
    )
    complexity_profile = CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY.get(
        difficulty_id,
        CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY["intermediate"],
    )
    problem_id = generate_token("cinfer")

    try:
        generated = service.problem_generator.generate_context_inference_problem_sync(
            problem_id=problem_id,
            track_id=track_id,
            language_id=language_id,
            difficulty=difficulty_choices[difficulty_id]["generator"],
            mode="context-inference",
            inference_type=inference_type,
            complexity_profile=complexity_profile,
            history_context=history_context,
        )
    except Exception as exc:  # pragma: no cover - network dependent path
        raise ValueError("맥락 추론 문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    expected_facets = normalize_str_list(generated.get("expected_facets"))
    reference_report = str(generated.get("reference_report") or "").strip()
    snippet = str(generated.get("snippet") or "").rstrip()
    prompt = str(generated.get("prompt") or "").strip()
    final_type = str(generated.get("inference_type") or inference_type).strip() or inference_type

    storage.append(
        {
            "type": "context_inference_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": "context-inference",
            "difficulty": difficulty_id,
            "title": generated.get("title"),
            "snippet": snippet,
            "prompt": prompt,
            "inference_type": final_type,
            "expected_facets": expected_facets,
            "reference_report": reference_report,
            "complexity_profile": complexity_profile,
            "created_at": utcnow(),
        }
    )

    return {
        "problemId": problem_id,
        "title": generated.get("title"),
        "language": language_id,
        "difficulty": difficulty_id,
        "snippet": snippet,
        "prompt": prompt,
        "inferenceType": final_type,
    }


def submit_context_inference_report(
    service: Any,
    username: str,
    problem_id: str,
    report: str,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    normalized_report = _normalize_report_text(report)

    storage = service._get_user_storage(username)
    instance = _load_mode_instance(
        storage,
        instance_type="context_inference_instance",
        problem_id=problem_id,
        missing_message="problemId가 올바르지 않습니다.",
    )

    expected_facets = normalize_str_list(instance.get("expected_facets"))
    reference_report = str(instance.get("reference_report") or "").strip()
    inference_type = str(instance.get("inference_type") or "").strip() or "pre_condition"

    try:
        evaluation = service.ai_client.analyze_context_inference_report(
            snippet=str(instance.get("snippet") or ""),
            prompt=str(instance.get("prompt") or ""),
            report=normalized_report,
            expected_facets=expected_facets,
            reference_report=reference_report,
            inference_type=inference_type,
            language=str(instance.get("language") or ""),
            difficulty=str(instance.get("difficulty") or ""),
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        evaluation = _fallback_report_evaluation(exc, missed_types=expected_facets)

    found_types = normalize_str_list((evaluation or {}).get("found_types"))
    missed_types = normalize_str_list((evaluation or {}).get("missed_types"))
    return _submit_report_mode(
        service,
        username,
        storage,
        instance,
        problem_id,
        normalized_report,
        evaluation,
        event_type="context_inference_event",
        mode="context-inference",
        pass_threshold=CONTEXT_INFERENCE_PASS_THRESHOLD,
        reference_report=reference_report,
        found_types=found_types,
        missed_types=missed_types,
        utcnow=utcnow,
        event_extra={"inference_type": inference_type},
    )


def request_refactoring_choice_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    track_id = default_track_id
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다.")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    history_context = service._refactoring_choice_history_context(storage)
    complexity_profile = REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY.get(
        difficulty_id,
        REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY["intermediate"],
    )
    constraint_count = REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY.get(difficulty_id, 3)
    problem_id = generate_token("rchoice")

    try:
        generated = service.problem_generator.generate_refactoring_choice_problem_sync(
            problem_id=problem_id,
            track_id=track_id,
            language_id=language_id,
            difficulty=difficulty_choices[difficulty_id]["generator"],
            mode="refactoring-choice",
            complexity_profile=complexity_profile,
            constraint_count=constraint_count,
            history_context=history_context,
            on_text_delta=on_text_delta,
        )
    except Exception as exc:  # pragma: no cover - network dependent path
        raise ValueError("최적의 선택 문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    title = str(generated.get("title") or "").strip() or "최적의 선택 문제"
    scenario = str(generated.get("scenario") or "").strip()
    prompt = str(generated.get("prompt") or "").strip() or "A/B/C 중 가장 적합한 코드를 선택하고 근거를 작성하세요."

    constraints = normalize_str_list(generated.get("constraints"))
    if len(constraints) > constraint_count:
        constraints = constraints[:constraint_count]
    while len(constraints) < constraint_count:
        constraints.append(f"제약 조건 {len(constraints) + 1}")

    options = normalize_refactoring_choice_options(
        generated.get("options"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_title_template="{option_id} 옵션",
        missing_code="def solution():\n    pass",
    )
    decision_facets = normalize_facets(
        generated.get("decision_facets"),
        taxonomy=REFACTORING_CHOICE_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )

    best_option = str(generated.get("best_option") or "A").strip().upper()
    if best_option not in REFACTORING_CHOICE_OPTION_IDS:
        best_option = "A"

    option_reviews = normalize_refactoring_choice_option_reviews(
        generated.get("option_reviews"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_summary_template="{option_id} 옵션의 장단점을 비교해 보세요.",
    )
    reference_report = str(generated.get("reference_report") or "").strip()
    if not reference_report:
        reference_report = (
            f"권장 선택지는 {best_option}입니다. "
            "제약 조건 대비 장단점을 비교하고 핵심 트레이드오프를 근거로 설명해야 합니다."
        )

    storage.append(
        {
            "type": "refactoring_choice_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": "refactoring-choice",
            "difficulty": difficulty_id,
            "title": title,
            "scenario": scenario,
            "constraints": constraints,
            "options": options,
            "prompt": prompt,
            "decision_facets": decision_facets,
            "best_option": best_option,
            "option_reviews": option_reviews,
            "reference_report": reference_report,
            "complexity_profile": complexity_profile,
            "created_at": utcnow(),
        }
    )

    return {
        "problemId": problem_id,
        "title": title,
        "language": language_id,
        "difficulty": difficulty_id,
        "scenario": scenario,
        "constraints": constraints,
        "options": options,
        "prompt": prompt,
        "decisionFacets": decision_facets,
    }


def submit_refactoring_choice_report(
    service: Any,
    username: str,
    problem_id: str,
    selected_option: str,
    report: str,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    normalized_report = _normalize_report_text(report)

    normalized_selected_option = str(selected_option or "").strip().upper()
    if normalized_selected_option not in REFACTORING_CHOICE_OPTION_IDS:
        raise ValueError("selectedOption은 A, B, C 중 하나여야 합니다.")

    storage = service._get_user_storage(username)
    instance = _load_mode_instance(
        storage,
        instance_type="refactoring_choice_instance",
        problem_id=problem_id,
        missing_message="problemId가 올바르지 않습니다.",
    )

    decision_facets = normalize_facets(
        instance.get("decision_facets"),
        taxonomy=REFACTORING_CHOICE_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )
    constraints = normalize_str_list(instance.get("constraints"))
    options = normalize_refactoring_choice_options(
        instance.get("options"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_title_template="{option_id} 옵션",
        missing_code="def solution():\n    pass",
    )
    best_option = str(instance.get("best_option") or "A").strip().upper()
    if best_option not in REFACTORING_CHOICE_OPTION_IDS:
        best_option = "A"
    option_reviews = normalize_refactoring_choice_option_reviews(
        instance.get("option_reviews"),
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_summary_template="{option_id} 옵션의 장단점을 비교해 보세요.",
    )
    reference_report = str(instance.get("reference_report") or "").strip()

    try:
        evaluation = service.ai_client.analyze_refactoring_choice_report(
            scenario=str(instance.get("scenario") or ""),
            prompt=str(instance.get("prompt") or ""),
            constraints=constraints,
            options=options,
            selected_option=normalized_selected_option,
            best_option=best_option,
            report=normalized_report,
            decision_facets=decision_facets,
            reference_report=reference_report,
            option_reviews=option_reviews,
            language=str(instance.get("language") or ""),
            difficulty=str(instance.get("difficulty") or ""),
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        evaluation = _fallback_report_evaluation(exc, missed_types=decision_facets)

    found_types, missed_types = _resolve_decision_type_results(
        evaluation,
        expected_types=decision_facets,
        report=normalized_report,
    )
    return _submit_report_mode(
        service,
        username,
        storage,
        instance,
        problem_id,
        normalized_report,
        evaluation,
        event_type="refactoring_choice_event",
        mode="refactoring-choice",
        pass_threshold=REFACTORING_CHOICE_PASS_THRESHOLD,
        reference_report=reference_report,
        found_types=found_types,
        missed_types=missed_types,
        utcnow=utcnow,
        event_extra={
            "selected_option": normalized_selected_option,
            "best_option": best_option,
            "option_reviews": option_reviews,
        },
        response_extra={
            "selectedOption": normalized_selected_option,
            "bestOption": best_option,
            "optionReviews": option_reviews,
        },
    )


def request_code_blame_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    track_id = default_track_id
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다.")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    history_context = service._code_blame_history_context(storage)
    candidate_count = CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY.get(difficulty_id, 4)
    culprit_count = select_weighted_count(count_weights=CODE_BLAME_CULPRIT_COUNT_WEIGHTS)
    problem_id = generate_token("cblame")

    try:
        generated = service.problem_generator.generate_code_blame_problem_sync(
            problem_id=problem_id,
            track_id=track_id,
            language_id=language_id,
            difficulty=difficulty_choices[difficulty_id]["generator"],
            mode="code-blame",
            candidate_count=candidate_count,
            culprit_count=culprit_count,
            decision_facets=list(CODE_BLAME_FACET_TAXONOMY),
            history_context=history_context,
            on_text_delta=on_text_delta,
        )
    except Exception as exc:  # pragma: no cover - network dependent path
        raise ValueError("범인 찾기 문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    title = str(generated.get("title") or "").strip() or "범인 찾기 문제"
    prompt = str(generated.get("prompt") or "").strip() or "에러 로그와 diff를 비교해 범인 커밋을 추리하세요."
    error_log = str(generated.get("error_log") or "").rstrip()
    commits = normalize_code_blame_commits(
        generated.get("commits"),
        candidate_count=candidate_count,
        option_ids=CODE_BLAME_OPTION_IDS,
        missing_title_template="Commit {option_id}",
        missing_diff="diff --git a/app.py b/app.py\n@@\n+pass",
    )
    option_ids = [row["optionId"] for row in commits]

    decision_facets = normalize_code_blame_facets(
        generated.get("decision_facets"),
        taxonomy=CODE_BLAME_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )
    culprit_commits = normalize_code_blame_option_ids(generated.get("culprit_commits"), option_ids)
    if culprit_count == 1:
        culprit_commits = culprit_commits[:1]
    else:
        culprit_commits = culprit_commits[:2]

    if not culprit_commits:
        culprit_commits = option_ids[: min(culprit_count, len(option_ids))]
    if culprit_count == 2 and len(culprit_commits) < 2 and len(option_ids) >= 2:
        culprit_commits = option_ids[:2]

    commit_reviews = normalize_code_blame_commit_reviews(
        generated.get("commit_reviews"),
        option_ids=option_ids,
        missing_summary_template="{option_id} 커밋의 위험도를 다시 점검해 보세요.",
    )
    reference_report = str(generated.get("reference_report") or "").strip()
    if not reference_report:
        culprit_label = ", ".join(culprit_commits)
        reference_report = (
            f"범인 커밋은 {culprit_label}입니다. "
            "로그 증거와 diff 변경점의 인과관계를 연결해 장애 메커니즘, 영향 범위, 검증/복구 전략을 설명하세요."
        )

    storage.append(
        {
            "type": "code_blame_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": "code-blame",
            "difficulty": difficulty_id,
            "title": title,
            "error_log": error_log,
            "commits": commits,
            "prompt": prompt,
            "decision_facets": decision_facets,
            "culprit_commits": culprit_commits,
            "commit_reviews": commit_reviews,
            "reference_report": reference_report,
            "candidate_count": candidate_count,
            "culprit_count": len(culprit_commits),
            "created_at": utcnow(),
        }
    )

    return {
        "problemId": problem_id,
        "title": title,
        "language": language_id,
        "difficulty": difficulty_id,
        "errorLog": error_log,
        "commits": commits,
        "prompt": prompt,
        "decisionFacets": decision_facets,
    }


def submit_code_blame_report(
    service: Any,
    username: str,
    problem_id: str,
    selected_commits: List[str],
    report: str,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    normalized_report = _normalize_report_text(report)

    storage = service._get_user_storage(username)
    instance = _load_mode_instance(
        storage,
        instance_type="code_blame_instance",
        problem_id=problem_id,
        missing_message="problemId가 올바르지 않습니다.",
    )

    candidate_count = int(instance.get("candidate_count") or len(instance.get("commits") or []) or 3)
    commits = normalize_code_blame_commits(
        instance.get("commits"),
        candidate_count=candidate_count,
        option_ids=CODE_BLAME_OPTION_IDS,
        missing_title_template="Commit {option_id}",
        missing_diff="diff --git a/app.py b/app.py\n@@\n+pass",
    )
    option_ids = [row["optionId"] for row in commits]
    normalized_selected_commits = normalize_code_blame_option_ids(selected_commits, option_ids)
    if not normalized_selected_commits:
        raise ValueError("selectedCommits를 최소 1개 선택해야 합니다.")
    if len(normalized_selected_commits) > 2:
        raise ValueError("selectedCommits는 최대 2개까지 선택할 수 있습니다.")

    culprit_commits = normalize_code_blame_option_ids(instance.get("culprit_commits"), option_ids)
    if not culprit_commits:
        culprit_commits = option_ids[:1]
    if len(culprit_commits) > 2:
        culprit_commits = culprit_commits[:2]

    decision_facets = normalize_code_blame_facets(
        instance.get("decision_facets"),
        taxonomy=CODE_BLAME_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )
    commit_reviews = normalize_code_blame_commit_reviews(
        instance.get("commit_reviews"),
        option_ids=option_ids,
        missing_summary_template="{option_id} 커밋의 위험도를 다시 점검해 보세요.",
    )
    reference_report = str(instance.get("reference_report") or "").strip()

    try:
        evaluation = service.ai_client.analyze_code_blame_report(
            error_log=str(instance.get("error_log") or ""),
            prompt=str(instance.get("prompt") or ""),
            commits=commits,
            selected_commits=normalized_selected_commits,
            culprit_commits=culprit_commits,
            report=normalized_report,
            decision_facets=decision_facets,
            reference_report=reference_report,
            commit_reviews=commit_reviews,
            language=str(instance.get("language") or ""),
            difficulty=str(instance.get("difficulty") or ""),
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        evaluation = _fallback_report_evaluation(exc, missed_types=decision_facets)

    found_types, missed_types = _resolve_decision_type_results(
        evaluation,
        expected_types=decision_facets,
        report=normalized_report,
    )
    return _submit_report_mode(
        service,
        username,
        storage,
        instance,
        problem_id,
        normalized_report,
        evaluation,
        event_type="code_blame_event",
        mode="code-blame",
        pass_threshold=CODE_BLAME_PASS_THRESHOLD,
        reference_report=reference_report,
        found_types=found_types,
        missed_types=missed_types,
        utcnow=utcnow,
        event_extra={
            "selected_commits": normalized_selected_commits,
            "culprit_commits": culprit_commits,
            "commit_reviews": commit_reviews,
        },
        response_extra={
            "selectedCommits": normalized_selected_commits,
            "culpritCommits": culprit_commits,
            "commitReviews": commit_reviews,
        },
    )


def submit_explanation(
    service: Any,
    username: str,
    language_id: str,
    problem_id: str,
    explanation: str,
    *,
    default_track_id: str,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    storage = service._get_user_storage(username)
    profile = service._ensure_profile(storage, username)
    profile = service._ensure_practice_ready(storage, username, profile)

    instance = service._get_problem_instance(storage, problem_id)
    if not instance:
        raise ValueError("요청한 문제를 찾을 수 없습니다. 다시 시도해주세요.")
    if instance.get("language") != language_id:
        raise ValueError("요청한 언어와 문제의 언어가 일치하지 않습니다.")
    if instance.get("track") != default_track_id:
        raise ValueError("현재 트랙에서 만든 문제가 아닙니다.")

    track_label = TRACKS.get(default_track_id, {}).get("title", default_track_id)
    language_label = LANGUAGES.get(language_id, {}).get("title", language_id)
    prompt = (
        "=== 문제 컨텍스트 ===\n"
        f"학습 트랙: {track_label} ({default_track_id})\n"
        f"문제 제목: {instance['title']}\n"
        f"언어: {language_label} ({language_id})\n"
        f"제공 코드:\n{instance['code']}\n\n"
        "=== 사용자 해설 ===\n"
        f"{explanation}"
    )
    feedback = service.ai_client.analyze(prompt)
    score = feedback.get("score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    feedback["score"] = score

    is_correct = feedback.get("correct")
    feedback["correct"] = is_correct

    storage.append(
        {
            "type": "learning_event",
            "track": instance.get("track", default_track_id),
            "language": language_id,
            "problem_id": problem_id,
            "mode": instance.get("mode"),
            "difficulty": instance.get("difficulty"),
            "explanation": explanation,
            "feedback": feedback,
            "score": score,
            "correct": is_correct,
            "created_at": utcnow(),
        }
    )

    storage.append(
        {
            "type": "memory",
            "track": instance.get("track", default_track_id),
            "language": language_id,
            "problem_id": problem_id,
            "summary": feedback.get("summary", ""),
            "strengths": feedback.get("strengths", []),
            "improvements": feedback.get("improvements", []),
            "score": score,
            "correct": is_correct,
            "created_at": utcnow(),
        }
    )

    profile = service._update_profile(
        storage,
        username,
        lambda data: service._profile_after_submission(
            data,
            problem_id,
            score,
            instance.get("mode"),
            is_correct,
        ),
    )
    service._update_tier_if_needed(storage, username)

    return {
        "feedback": feedback,
        "skillLevel": normalize_skill_level(profile.get("skill_level"), DEFAULT_SKILL_LEVEL),
        "model_answer": instance.get("reference", "모범 답안이 없습니다."),
    }


def request_code_arrange_problem(
    service: Any,
    username: str,
    language_id: str,
    difficulty_id: str,
    *,
    default_track_id: str,
    difficulty_choices: Dict[str, Dict[str, str]],
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    track_id = default_track_id
    if language_id not in LANGUAGES:
        raise ValueError("지원하지 않는 언어입니다.")
    if difficulty_id not in difficulty_choices:
        raise ValueError("지원하지 않는 난이도입니다.")

    storage = service._get_user_storage(username)
    history_context = service._code_arrange_history_context(storage)

    problem_id = generate_token("carrange")
    generated = service.problem_generator.generate_sync(
        problem_id=problem_id,
        track_id=track_id,
        language_id=language_id,
        difficulty=difficulty_choices[difficulty_id]["generator"],
        mode="code-arrange",
        history_context=history_context,
        retry_context=None,
    )

    blocks = service._chunk_and_shuffle_code(generated.code)
    correct_order = [blk["id"] for blk in blocks["ordered"]]
    shuffled_blocks = blocks["shuffled"]

    storage.append(
        {
            "type": "code_arrange_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "difficulty": difficulty_id,
            "title": generated.title,
            "code": generated.code,
            "blocks": blocks["ordered"],
            "correct_order": correct_order,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    return {
        "problemId": problem_id,
        "title": generated.title,
        "language": language_id,
        "blocks": shuffled_blocks,
    }


def submit_code_arrange_answer(
    service: Any,
    username: str,
    problem_id: str,
    order: List[str],
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    storage = service._get_user_storage(username)
    instance = storage.find_one(
        lambda item: item.get("type") == "code_arrange_instance" and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError("해당 코드 배치 문제를 찾지 못했습니다.")

    correct_order: List[str] = instance.get("correct_order") or []
    if not order or len(order) != len(correct_order):
        raise ValueError("제출된 블록 순서가 올바르지 않습니다.")

    results = []
    is_correct_overall = True
    for expected, submitted in zip(correct_order, order):
        block_correct = expected == submitted
        results.append({"id": submitted, "correct": block_correct})
        if not block_correct:
            is_correct_overall = False

    _record_mode_event(
        service,
        storage,
        username,
        event_type="code_arrange_event",
        problem_id=problem_id,
        instance=instance,
        utcnow=utcnow,
        event_extra={
            "submitted_order": order,
            "correct_order": correct_order,
            "correct": is_correct_overall,
        },
    )

    block_map = {blk["id"]: blk["code"] for blk in (instance.get("blocks") or [])}
    answer_code = "\n".join(block_map.get(block_id, "") for block_id in correct_order).strip()

    return {
        "correct": is_correct_overall,
        "results": results,
        "answerOrder": correct_order,
        "answerCode": answer_code,
    }


class LearningService:
    """Handle diagnostics, problem generation, and feedback persistence."""

    def __init__(
        self,
        storage_manager: UserStorageManager,
        ai_client: Optional[AIClient] = None,
        problem_generator: Optional[ProblemGenerator] = None,
    ):
        self.storage_manager = storage_manager
        self.ai_client = ai_client or AIClient()
        self.problem_generator = problem_generator or ProblemGenerator()

    # Catalog lookups -----------------------------------------------------

    def list_tracks(self) -> List[Dict[str, str]]:
        languages = list(LANGUAGES.keys())
        return [
            {
                "id": key,
                "title": meta["title"],
                "description": meta["description"],
                "languages": languages,
            }
            for key, meta in TRACKS.items()
        ]

    def list_languages(self) -> List[Dict[str, str]]:
        return [
            {"id": key, "title": meta["title"], "description": meta["description"]}
            for key, meta in LANGUAGES.items()
        ]

    # Profile -------------------------------------------------------------

    def get_profile(self, username: str) -> Dict[str, Any]:
        storage = self._get_user_storage(username)
        profile = self._ensure_profile(storage, username)
        profile = self._ensure_practice_ready(storage, username, profile)
        answered = len(profile.get("diagnostic_results", []))
        pending = len(profile.get("pending_problems", []))
        total = profile.get("diagnostic_total", DEFAULT_DIAGNOSTIC_TOTAL)
        remaining = max(total - answered, 0)
        events = storage.filter(
            lambda item: item.get("type") == "learning_event" and item.get("mode") != "code-block"
        )
        attempts = len(events)
        correct = sum(1 for event in events if event.get("correct") is True)
        accuracy = round((correct / attempts) * 100, 1) if attempts else 0.0

        return {
            "username": username,
            "skillLevel": normalize_skill_level(profile.get("skill_level"), DEFAULT_SKILL_LEVEL),
            "diagnosticCompleted": profile.get("diagnostic_completed", False),
            "diagnosticTotal": total,
            "diagnosticAnswered": answered,
            "diagnosticPending": pending,
            "diagnosticRemaining": remaining,
            "totalAttempts": attempts,
            "correctAnswers": correct,
            "accuracy": accuracy,
        }

    # Problem lifecycle ---------------------------------------------------
    async def request_problem_async(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_problem, username, language_id, difficulty_id)

    async def request_code_block_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_block_problem, username, language_id, difficulty_id)

    async def request_code_arrange_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_arrange_problem, username, language_id, difficulty_id)

    async def request_code_error_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_error_problem, username, language_id, difficulty_id)

    async def request_auditor_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_auditor_problem, username, language_id, difficulty_id)

    async def request_context_inference_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_context_inference_problem, username, language_id, difficulty_id)

    async def request_refactoring_choice_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_refactoring_choice_problem, username, language_id, difficulty_id)

    async def request_code_blame_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_code_blame_problem, username, language_id, difficulty_id)

    async def request_single_file_analysis_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_single_file_analysis_problem, username, language_id, difficulty_id)

    async def request_multi_file_analysis_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_multi_file_analysis_problem, username, language_id, difficulty_id)

    async def request_fullstack_analysis_problem_async(
        self, username: str, language_id: str, difficulty_id: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.request_fullstack_analysis_problem, username, language_id, difficulty_id)


    async def submit_explanation_async(
        self,
        username: str,
        language_id: str,
        problem_id: str,
        explanation: str,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_explanation, username, language_id, problem_id, explanation)

    async def submit_code_block_answer_async(
        self, username: str, problem_id: str, selected_option: int
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_code_block_answer, username, problem_id, selected_option)

    async def submit_code_arrange_answer_async(
        self, username: str, problem_id: str, order: List[str]
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_code_arrange_answer, username, problem_id, order)

    async def submit_code_error_answer_async(
        self, username: str, problem_id: str, selected_index: int
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_code_error_answer, username, problem_id, selected_index)

    async def submit_auditor_report_async(
        self, username: str, problem_id: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_auditor_report, username, problem_id, report)

    async def submit_context_inference_report_async(
        self, username: str, problem_id: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_context_inference_report, username, problem_id, report)

    async def submit_refactoring_choice_report_async(
        self, username: str, problem_id: str, selected_option: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.submit_refactoring_choice_report,
            username,
            problem_id,
            selected_option,
            report,
        )

    async def submit_code_blame_report_async(
        self, username: str, problem_id: str, selected_commits: List[str], report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.submit_code_blame_report,
            username,
            problem_id,
            selected_commits,
            report,
        )

    async def submit_single_file_analysis_report_async(
        self, username: str, problem_id: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_single_file_analysis_report, username, problem_id, report)

    async def submit_multi_file_analysis_report_async(
        self, username: str, problem_id: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_multi_file_analysis_report, username, problem_id, report)

    async def submit_fullstack_analysis_report_async(
        self, username: str, problem_id: str, report: str
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self.submit_fullstack_analysis_report, username, problem_id, report)

    def request_problem(
        self,
        username: str,
        language_id: str,
        difficulty_id: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
            on_text_delta=on_text_delta,
        )

    def request_code_block_problem(
        self,
        username: str,
        language_id: str,
        difficulty_id: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_code_block_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
            on_text_delta=on_text_delta,
        )

    def submit_code_block_answer(self, username: str, problem_id: str, selected_option: int) -> Dict[str, Any]:
        return submit_code_block_answer(
            self,
            username,
            problem_id,
            selected_option,
            default_track_id=DEFAULT_TRACK_ID,
            utcnow=_utcnow,
        )

    def request_code_error_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_code_error_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def submit_code_error_answer(self, username: str, problem_id: str, selected_index: int) -> Dict[str, Any]:
        return submit_code_error_answer(
            self,
            username,
            problem_id,
            selected_index,
            utcnow=_utcnow,
        )

    def request_auditor_problem(
        self,
        username: str,
        language_id: str,
        difficulty_id: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_auditor_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
            on_text_delta=on_text_delta,
        )

    def request_context_inference_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_context_inference_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def request_refactoring_choice_problem(
        self,
        username: str,
        language_id: str,
        difficulty_id: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_refactoring_choice_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
            on_text_delta=on_text_delta,
        )

    def request_code_blame_problem(
        self,
        username: str,
        language_id: str,
        difficulty_id: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_code_blame_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
            on_text_delta=on_text_delta,
        )

    def request_single_file_analysis_problem(
        self,
        username: str,
        language_id: str,
        difficulty_id: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_single_file_analysis_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
            on_text_delta=on_text_delta,
        )

    def request_multi_file_analysis_problem(
        self,
        username: str,
        language_id: str,
        difficulty_id: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_multi_file_analysis_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
            on_text_delta=on_text_delta,
        )

    def request_fullstack_analysis_problem(
        self,
        username: str,
        language_id: str,
        difficulty_id: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_fullstack_analysis_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
            on_text_delta=on_text_delta,
        )

    def submit_auditor_report(self, username: str, problem_id: str, report: str) -> Dict[str, Any]:
        return submit_auditor_report(
            self,
            username,
            problem_id,
            report,
            utcnow=_utcnow,
        )

    def submit_context_inference_report(self, username: str, problem_id: str, report: str) -> Dict[str, Any]:
        return submit_context_inference_report(
            self,
            username,
            problem_id,
            report,
            utcnow=_utcnow,
        )

    def submit_refactoring_choice_report(
        self,
        username: str,
        problem_id: str,
        selected_option: str,
        report: str,
    ) -> Dict[str, Any]:
        return submit_refactoring_choice_report(
            self,
            username,
            problem_id,
            selected_option,
            report,
            utcnow=_utcnow,
        )

    def submit_code_blame_report(
        self,
        username: str,
        problem_id: str,
        selected_commits: List[str],
        report: str,
    ) -> Dict[str, Any]:
        return submit_code_blame_report(
            self,
            username,
            problem_id,
            selected_commits,
            report,
            utcnow=_utcnow,
        )

    def submit_single_file_analysis_report(self, username: str, problem_id: str, report: str) -> Dict[str, Any]:
        return submit_single_file_analysis_report(
            self,
            username,
            problem_id,
            report,
            utcnow=_utcnow,
        )

    def submit_multi_file_analysis_report(self, username: str, problem_id: str, report: str) -> Dict[str, Any]:
        return submit_multi_file_analysis_report(
            self,
            username,
            problem_id,
            report,
            utcnow=_utcnow,
        )

    def submit_fullstack_analysis_report(self, username: str, problem_id: str, report: str) -> Dict[str, Any]:
        return submit_fullstack_analysis_report(
            self,
            username,
            problem_id,
            report,
            utcnow=_utcnow,
        )

    def submit_explanation(
        self,
        username: str,
        language_id: str,
        problem_id: str,
        explanation: str,
    ) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return submit_explanation(
            self,
            username,
            language_id,
            problem_id,
            explanation,
            default_track_id=DEFAULT_TRACK_ID,
            utcnow=_utcnow,
        )

    def request_code_arrange_problem(self, username: str, language_id: str, difficulty_id: str) -> Dict[str, Any]:
        language_id = _normalize_requested_language(language_id)
        return request_code_arrange_problem(
            self,
            username,
            language_id,
            difficulty_id,
            default_track_id=DEFAULT_TRACK_ID,
            difficulty_choices=DIFFICULTY_CHOICES,
            utcnow=_utcnow,
        )

    def submit_code_arrange_answer(self, username: str, problem_id: str, order: List[str]) -> Dict[str, Any]:
        return submit_code_arrange_answer(
            self,
            username,
            problem_id,
            order,
            utcnow=_utcnow,
        )

    # Reporting -----------------------------------------------------------

    def user_history(self, username: str, limit: int | None = None) -> List[Dict[str, Any]]:
        return learning_reporting.user_history(
            self,
            username,
            duration_seconds=_duration_seconds,
            limit=limit,
        )

    def user_memory(self, username: str) -> List[Dict[str, Any]]:
        storage = self._get_user_storage(username)
        memory_entries = storage.filter(lambda item: item.get("type") == "memory")
        return sorted(memory_entries, key=lambda item: item.get("created_at", ""), reverse=True)

    def learning_report(self, username: str) -> Dict[str, Any]:
        return learning_reporting.learning_report(
            self,
            username,
            accuracy_from_events=_accuracy_from_events,
            duration_seconds=_duration_seconds,
        )


    # Internal helpers ----------------------------------------------------

    def _get_user_storage(self, username: str):
        try:
            return self.storage_manager.get_storage(username)
        except FileNotFoundError as exc:
            raise ValueError("사용자 저장소를 찾을 수 없습니다.") from exc

    def _ensure_profile(self, storage, username: str) -> Dict[str, Any]:
        profile = storage.find_one(lambda item: item.get("type") == "profile")
        if profile:
            return profile
        default = _default_profile(username)
        storage.append(default)
        return default

    def _update_profile(self, storage, username: str, mutator) -> Dict[str, Any]:
        def predicate(item: Dict[str, Any]) -> bool:
            return item.get("type") == "profile"

        def updater(current: Dict[str, Any]) -> Dict[str, Any]:
            profile = dict(current)
            mutator(profile)
            profile["updated_at"] = _utcnow()
            return profile

        updated = storage.update_record(predicate, updater)
        if updated is not None:
            return updated

        profile = _default_profile(username)
        mutator(profile)
        profile["updated_at"] = _utcnow()
        storage.append(profile)
        return profile

    def _profile_after_assignment(self, profile: Dict[str, Any], problem_id: str, diagnostic: bool) -> Dict[str, Any]:
        pending = list(profile.get("pending_problems", []))
        pending.append(problem_id)
        profile["pending_problems"] = pending
        if diagnostic:
            profile["diagnostic_given"] = int(profile.get("diagnostic_given", 0)) + 1
        return profile

    def _profile_after_submission(
        self,
        profile: Dict[str, Any],
        problem_id: str,
        score: Optional[float],
        mode: Optional[str],
        is_correct: Optional[bool],
    ) -> Dict[str, Any]:
        profile["pending_problems"] = [
            pid for pid in profile.get("pending_problems", []) if pid != problem_id
        ]

        stats = dict(profile.get("stats", {"attempts": 0, "correct": 0}))
        stats["attempts"] = int(stats.get("attempts", 0)) + 1
        if is_correct is True:
            stats["correct"] = int(stats.get("correct", 0)) + 1
        else:
            stats["correct"] = int(stats.get("correct", 0))
        profile["stats"] = stats

        if mode == "diagnostic":
            score_value = float(score) if score is not None else 50.0
            results = list(profile.get("diagnostic_results", []))
            results.append(
                {
                    "problem_id": problem_id,
                    "score": score_value,
                    "correct": is_correct,
                    "created_at": _utcnow(),
                }
            )
            profile["diagnostic_results"] = results

            total = max(profile.get("diagnostic_total", DEFAULT_DIAGNOSTIC_TOTAL), 1)
            if len(results) >= total:
                average_points = sum(item.get("score", 0.0) for item in results[-total:]) / total
                profile["skill_level"] = self._score_to_level(average_points / 100.0)
                profile["diagnostic_completed"] = True

        if profile.get("diagnostic_completed") and not profile.get("skill_level"):
            profile["skill_level"] = DEFAULT_SKILL_LEVEL

        return profile

    def _ensure_practice_ready(self, storage, username: str, profile: Dict[str, Any]) -> Dict[str, Any]:
        if profile.get("diagnostic_completed", False):
            return profile
        return self._update_profile(storage, username, self._mark_practice_ready)

    def _mark_practice_ready(self, profile: Dict[str, Any]) -> None:
        profile["diagnostic_completed"] = True
        profile["diagnostic_total"] = 0
        profile["diagnostic_given"] = 0
        profile["diagnostic_results"] = []

    def _score_to_level(self, score: float) -> str:
        return score_to_skill_level(score, DEFAULT_SKILL_LEVEL)

    def _accuracy_to_level(self, accuracy: float) -> str:
        return score_to_skill_level(accuracy, DEFAULT_SKILL_LEVEL)

    def _collect_attempt_events(self, storage) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        events.extend(storage.filter(lambda item: item.get("type") == "learning_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "code_calc_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "code_error_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "code_arrange_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "auditor_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "context_inference_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "refactoring_choice_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "code_blame_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "single_file_analysis_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "multi_file_analysis_event"))
        events.extend(storage.filter(lambda item: item.get("type") == "fullstack_analysis_event"))
        return events

    def _instances_by_id(self, storage) -> Dict[str, Dict[str, Any]]:
        instances: Dict[str, Dict[str, Any]] = {}
        for item in storage.filter(lambda it: it.get("type") == "problem_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_block_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_calc_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_error_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_arrange_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "auditor_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "context_inference_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "refactoring_choice_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "code_blame_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "single_file_analysis_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "multi_file_analysis_instance"):
            instances[item.get("problem_id")] = item
        for item in storage.filter(lambda it: it.get("type") == "fullstack_analysis_instance"):
            instances[item.get("problem_id")] = item
        return instances

    def _recent_attempts(self, storage, limit: int = TIER_REVIEW_WINDOW) -> List[Dict[str, Any]]:
        return learning_tier.recent_attempts(self, storage, limit=limit)

    def _update_tier_if_needed(self, storage, username: str) -> None:
        learning_tier.update_tier_if_needed(
            self,
            storage,
            username,
            tier_review_window=TIER_REVIEW_WINDOW,
            tier_beginner_ratio_limit=TIER_BEGINNER_RATIO_LIMIT,
            utcnow=_utcnow,
        )


    def _get_problem_instance(self, storage, problem_id: str) -> Optional[Dict[str, Any]]:
        return storage.find_one(
            lambda item: item.get("type") == "problem_instance" and item.get("problem_id") == problem_id
        )

    def _code_block_history_context(self, storage, limit: int = 5) -> Optional[str]:
        instances = storage.filter(lambda item: item.get("type") == "code_block_instance")
        if not instances:
            return None
        sorted_items = sorted(instances, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "제목 없음"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            first_line = (item.get("code") or "").splitlines()[0] if item.get("code") else ""
            lines.append(f"{idx}. {lang}/{diff} · {title} · 코드 첫 줄: {first_line}")
        return "\n".join(lines)

    def get_problem_hint(self, username: str, problem_id: str) -> Dict[str, str]:
        storage = self._get_user_storage(username)
        instance = self._get_problem_instance(storage, problem_id)
        if not instance:
            raise ValueError("요청한 문제를 찾을 수 없습니다. 다시 불러와 주세요.")

        reference = instance.get("reference") or ""
        prompt = instance.get("prompt") or ""
        source = reference or prompt or "힌트가 준비되지 않았습니다."
        return {"hint": _lighten_hint(source)}

    def _get_last_learning_event(self, storage) -> Optional[Dict[str, Any]]:
        events = storage.filter(
            lambda item: item.get("type") == "learning_event" and item.get("mode") != "code-block"
        )
        if not events:
            return None
        # Sort by created_at descending and take the first one
        return sorted(events, key=lambda item: item.get("created_at", ""), reverse=True)[0]

    def _problem_history_context(self, storage, limit: int = 5) -> Optional[str]:
        """Summarize recent learning events so the generator can avoid duplicates."""

        events = storage.filter(
            lambda item: item.get("type") == "learning_event" and item.get("mode") != "code-block"
        )
        if not events:
            return None

        instances = {
            item.get("problem_id"): item
            for item in storage.filter(lambda entry: entry.get("type") == "problem_instance")
        }

        sorted_events = sorted(events, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, event in enumerate(sorted_events, start=1):
            language_id = event.get("language")
            language_label = LANGUAGES.get(language_id, {}).get("title", language_id or "-")
            difficulty = event.get("difficulty") or "-"
            verdict = event.get("correct")
            verdict_label = "정답" if verdict is True else "오답" if verdict is False else "미정"
            instance = instances.get(event.get("problem_id")) or {}
            title = instance.get("title") or ""
            prompt = instance.get("prompt") or ""
            feedback = event.get("feedback") or {}
            summary = ""
            if isinstance(feedback, dict):
                summary = feedback.get("summary") or ""
            if not summary:
                summary = prompt or (event.get("explanation") or "")[:160]
            summary = summary.replace("\n", " ").strip()
            topic = title or prompt.splitlines()[0] if prompt else ""
            duration = _duration_seconds(instance.get("created_at"), event.get("created_at"))
            duration_label = f"{int(duration)}초" if duration is not None else "시간 미기록"
            lines.append(
                f"{idx}. {language_label}/{difficulty} · {verdict_label} · "
                f"주제: {topic or '제목 없음'} · 요약: {summary} · 소요시간: {duration_label}"
            )
        return "\n".join(lines)

    def _code_error_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "code_error_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "미정 제목"
            lang = item.get("language") or "-"
            sample = (item.get("blocks") or [])
            first = sample[0].splitlines()[0] if sample else ""
            lines.append(f"{idx}. {lang} · {title} · 첫줄: {first}")
        return "\n".join(lines)

    def _code_arrange_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "code_arrange_instance")
        if not items:
            return None

        latest_event_by_problem_id: Dict[str, Dict[str, Any]] = {}
        arrange_events = storage.filter(lambda item: item.get("type") == "code_arrange_event")
        for event in sorted(arrange_events, key=lambda item: item.get("created_at", ""), reverse=True):
            problem_id = str(event.get("problem_id") or "").strip()
            if problem_id and problem_id not in latest_event_by_problem_id:
                latest_event_by_problem_id[problem_id] = event

        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            first_line = (item.get("code") or "").splitlines()[0] if item.get("code") else ""
            problem_id = str(item.get("problem_id") or "").strip()
            event = latest_event_by_problem_id.get(problem_id)
            verdict = "unsolved"
            if event:
                if event.get("correct") is True:
                    verdict = "correct"
                elif event.get("correct") is False:
                    verdict = "wrong"
            lines.append(f"{idx}. {lang}/{diff} - {verdict} - {title} - first line: {first_line}")
        return "\n".join(lines)

    def _auditor_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "auditor_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            trap_count = item.get("trap_count") or len(item.get("trap_catalog") or [])
            first_line = (item.get("code") or "").splitlines()[0] if item.get("code") else ""
            lines.append(f"{idx}. {lang}/{diff} - traps {trap_count} - {title} - first line: {first_line}")
        return "\n".join(lines)

    def _context_inference_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "context_inference_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            inference_type = item.get("inference_type") or "-"
            first_line = (item.get("snippet") or "").splitlines()[0] if item.get("snippet") else ""
            lines.append(f"{idx}. {lang}/{diff} - {inference_type} - {title} - first line: {first_line}")
        return "\n".join(lines)

    def _refactoring_choice_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "refactoring_choice_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            best_option = item.get("best_option") or "-"
            scenario = (item.get("scenario") or "").splitlines()[0] if item.get("scenario") else ""
            lines.append(f"{idx}. {lang}/{diff} - best {best_option} - {title} - scenario: {scenario}")
        return "\n".join(lines)

    def _code_blame_history_context(self, storage, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == "code_blame_instance")
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            commit_count = len(item.get("commits") or [])
            log_head = (item.get("error_log") or "").splitlines()[0] if item.get("error_log") else ""
            lines.append(f"{idx}. {lang}/{diff} - commits {commit_count} - {title} - log: {log_head}")
        return "\n".join(lines)

    def _advanced_analysis_history_context(self, storage, instance_type: str, limit: int = 5) -> Optional[str]:
        items = storage.filter(lambda item: item.get("type") == instance_type)
        if not items:
            return None
        sorted_items = sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]
        lines: List[str] = []
        for idx, item in enumerate(sorted_items, 1):
            title = item.get("title") or "Untitled"
            lang = item.get("language") or "-"
            diff = item.get("difficulty") or "-"
            files = item.get("files") or []
            file_count = len(files) if isinstance(files, list) else 0
            first_path = ""
            if isinstance(files, list) and files:
                first = files[0]
                if isinstance(first, dict):
                    first_path = str(first.get("path") or first.get("name") or "")
            lines.append(f"{idx}. {lang}/{diff} - files {file_count} - {title} - first: {first_path}")
        return "\n".join(lines)

    def _single_file_analysis_history_context(self, storage, limit: int = 5) -> Optional[str]:
        return self._advanced_analysis_history_context(storage, "single_file_analysis_instance", limit=limit)

    def _multi_file_analysis_history_context(self, storage, limit: int = 5) -> Optional[str]:
        return self._advanced_analysis_history_context(storage, "multi_file_analysis_instance", limit=limit)

    def _fullstack_analysis_history_context(self, storage, limit: int = 5) -> Optional[str]:
        return self._advanced_analysis_history_context(storage, "fullstack_analysis_instance", limit=limit)

    def _chunk_and_shuffle_code(self, code: str) -> Dict[str, Any]:
        """Split code into 2~3 line chunks, keep correct order, and return a shuffled variant."""

        raw_lines = [line for line in (code or "").splitlines() if line.strip() != ""]
        chunks: List[List[str]] = []
        idx = 0
        while idx < len(raw_lines):
            remaining = len(raw_lines) - idx
            group_size = 3 if remaining >= 5 else 2 if remaining >= 2 else 1
            chunk = raw_lines[idx : idx + group_size]
            chunks.append(chunk)
            idx += group_size

        ordered_blocks = []
        for i, chunk in enumerate(chunks):
            ordered_blocks.append({"id": f"blk-{i+1}", "code": "\n".join(chunk)})

        shuffled_blocks = ordered_blocks.copy()
        random.shuffle(shuffled_blocks)

        return {"ordered": ordered_blocks, "shuffled": shuffled_blocks}

    def _build_report_recommendations(
        self,
        history: List[Dict[str, Any]],
        strengths: Dict[str, int],
        improvements: Dict[str, int],
    ) -> List[str]:
        recommendations: List[str] = []
        recent_incorrect = [event for event in history if event.get("correct") is False][:3]
        if recent_incorrect:
            failed_topics = ", ".join(
                f"{LANGUAGES.get(evt.get('language'), {}).get('title', evt.get('language', '-'))}/{evt.get('difficulty')}"
                for evt in recent_incorrect
            )
            recommendations.append(f"최근 틀린 주제 다시 보기: {failed_topics}")

        if strengths:
            top_strength = max(strengths.items(), key=lambda item: item[1])[0]
            recommendations.append(f"강점 보강: '{top_strength}' 문제를 더 풀어보세요.")

        if improvements:
            top_gap = max(improvements.items(), key=lambda item: item[1])[0]
            recommendations.append(f"취약 보완: '{top_gap}' 유형을 집중 연습하세요.")

        if not recommendations:
            recommendations.append("추가 권장 사항이 없습니다. 현재 페이스를 유지하세요.")
        return recommendations


def list_public_languages() -> list[dict[str, str]]:
    from server.features.learning.history import list_public_languages as _impl

    return _impl()


def get_public_me(current: Any) -> dict[str, Any]:
    from server.features.learning.history import get_public_me as _impl

    return _impl(current)


def get_public_memory(username: str) -> list[dict[str, Any]]:
    from server.features.learning.history import get_public_memory as _impl

    return _impl(username)


def get_public_history(username: str, limit: int | None = None) -> list[dict[str, Any]]:
    from server.features.learning.history import get_public_history as _impl

    return _impl(username, limit=limit)


def get_public_history_page(username: str, limit: int | None = None) -> dict[str, Any]:
    from server.features.learning.history import get_public_history_page as _impl

    return _impl(username, limit=limit)


def get_public_profile(username: str, history_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from server.features.learning.history import get_public_profile as _impl

    return _impl(username, history_rows=history_rows)


def get_public_report(username: str, user_id: int, db: Any = None) -> dict[str, Any]:
    from server.features.learning.history import get_public_report as _impl

    return _impl(username, user_id, db)


def request_mode_problem(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from server.features.learning.history import request_mode_problem as _impl

    return _impl(*args, **kwargs)


def submit_mode_answer(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from server.features.learning.history import submit_mode_answer as _impl

    return _impl(*args, **kwargs)
