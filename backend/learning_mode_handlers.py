from __future__ import annotations

from typing import Any, Callable, Dict, List

from backend.content import LANGUAGES, TRACKS
from backend.mode_normalization import (
    normalize_code_blame_commit_reviews as _shared_normalize_code_blame_commit_reviews,
    normalize_code_blame_commits as _shared_normalize_code_blame_commits,
    normalize_code_blame_facets as _shared_normalize_code_blame_facets,
    normalize_code_blame_option_ids as _shared_normalize_code_blame_option_ids,
    normalize_facets as _shared_normalize_facets,
    normalize_refactoring_choice_option_reviews as _shared_normalize_refactoring_choice_option_reviews,
    normalize_refactoring_choice_options as _shared_normalize_refactoring_choice_options,
    normalize_str_list as _shared_normalize_str_list,
    select_context_inference_type as _shared_select_context_inference_type,
    select_weighted_count as _shared_select_weighted_count,
)
from backend.mode_policies import (
    AUDITOR_TRAP_COUNT_BY_DIFFICULTY as POLICY_AUDITOR_TRAP_COUNT_BY_DIFFICULTY,
    CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY as POLICY_CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY,
    CODE_BLAME_CULPRIT_COUNT_WEIGHTS as POLICY_CODE_BLAME_CULPRIT_COUNT_WEIGHTS,
    CODE_BLAME_FACET_TAXONOMY as POLICY_CODE_BLAME_FACET_TAXONOMY,
    CODE_BLAME_OPTION_IDS as POLICY_CODE_BLAME_OPTION_IDS,
    CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY as POLICY_CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
    CONTEXT_INFERENCE_TYPE_WEIGHTS as POLICY_CONTEXT_INFERENCE_TYPE_WEIGHTS,
    MODE_PASS_THRESHOLD,
    REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY as POLICY_REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
    REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY as POLICY_REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY,
    REFACTORING_CHOICE_FACET_TAXONOMY as POLICY_REFACTORING_CHOICE_FACET_TAXONOMY,
    REFACTORING_CHOICE_OPTION_IDS as POLICY_REFACTORING_CHOICE_OPTION_IDS,
)
from backend.security import generate_token


AUDITOR_TRAP_COUNT_BY_DIFFICULTY = POLICY_AUDITOR_TRAP_COUNT_BY_DIFFICULTY
AUDITOR_PASS_THRESHOLD = MODE_PASS_THRESHOLD

CONTEXT_INFERENCE_PASS_THRESHOLD = MODE_PASS_THRESHOLD
CONTEXT_INFERENCE_TYPE_WEIGHTS = POLICY_CONTEXT_INFERENCE_TYPE_WEIGHTS
CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY = POLICY_CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY

REFACTORING_CHOICE_PASS_THRESHOLD = MODE_PASS_THRESHOLD
REFACTORING_CHOICE_OPTION_IDS = POLICY_REFACTORING_CHOICE_OPTION_IDS
REFACTORING_CHOICE_FACET_TAXONOMY = POLICY_REFACTORING_CHOICE_FACET_TAXONOMY
REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY = POLICY_REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY
REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY = POLICY_REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY

CODE_BLAME_PASS_THRESHOLD = MODE_PASS_THRESHOLD
CODE_BLAME_OPTION_IDS = POLICY_CODE_BLAME_OPTION_IDS
CODE_BLAME_FACET_TAXONOMY = POLICY_CODE_BLAME_FACET_TAXONOMY
CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY = POLICY_CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY
CODE_BLAME_CULPRIT_COUNT_WEIGHTS = POLICY_CODE_BLAME_CULPRIT_COUNT_WEIGHTS

ADVANCED_ANALYSIS_PASS_THRESHOLD = MODE_PASS_THRESHOLD


def select_context_inference_type(difficulty_id: str) -> str:
    return _shared_select_context_inference_type(
        difficulty_id,
        weights_by_difficulty=CONTEXT_INFERENCE_TYPE_WEIGHTS,
        default_difficulty="intermediate",
    )


def _normalize_str_list(value: object) -> list[str]:
    return _shared_normalize_str_list(value)


def _normalize_refactoring_choice_options(value: object) -> list[dict[str, str]]:
    return _shared_normalize_refactoring_choice_options(
        value,
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_title_template="{option_id} 옵션",
        missing_code="def solution():\n    pass",
    )


def _normalize_refactoring_choice_option_reviews(value: object) -> list[dict[str, str]]:
    return _shared_normalize_refactoring_choice_option_reviews(
        value,
        option_ids=REFACTORING_CHOICE_OPTION_IDS,
        missing_summary_template="{option_id} 옵션의 장단점을 비교해 보세요.",
    )


def _normalize_refactoring_choice_facets(value: object) -> list[str]:
    return _shared_normalize_facets(
        value,
        taxonomy=REFACTORING_CHOICE_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )


def select_code_blame_culprit_count() -> int:
    return _shared_select_weighted_count(count_weights=CODE_BLAME_CULPRIT_COUNT_WEIGHTS)


def _normalize_code_blame_commits(value: object, candidate_count: int) -> list[dict[str, str]]:
    return _shared_normalize_code_blame_commits(
        value,
        candidate_count=candidate_count,
        option_ids=CODE_BLAME_OPTION_IDS,
        missing_title_template="Commit {option_id}",
        missing_diff="diff --git a/app.py b/app.py\n@@\n+pass",
    )


def _normalize_code_blame_option_ids(value: object, allowed_ids: list[str] | tuple[str, ...]) -> list[str]:
    return _shared_normalize_code_blame_option_ids(
        value,
        allowed_ids=allowed_ids,
    )


def _normalize_code_blame_commit_reviews(value: object, option_ids: list[str]) -> list[dict[str, str]]:
    return _shared_normalize_code_blame_commit_reviews(
        value,
        option_ids=option_ids,
        missing_summary_template="{option_id} 커밋의 위험도를 다시 점검해 보세요.",
    )


def _normalize_code_blame_facets(value: object) -> list[str]:
    return _shared_normalize_code_blame_facets(
        value,
        taxonomy=CODE_BLAME_FACET_TAXONOMY,
        min_count=3,
        max_count=4,
    )


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


def request_problem(
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
        "skillLevel": profile.get("skill_level", "beginner"),
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

    storage.append(
        {
            "type": "learning_event",
            "track": instance.get("track", default_track_id),
            "language": instance.get("language"),
            "problem_id": problem_id,
            "mode": "code-block",
            "difficulty": instance.get("difficulty"),
            "selected_option": selected_option,
            "correct_answer_index": correct_answer_index,
            "correct": is_correct,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    return {
        "correct": is_correct,
        "correctAnswer": correct_answer_index,
        "explanation": instance.get("explanation"),
        "skillLevel": profile.get("skill_level", "beginner"),
    }


def request_code_calc_problem(
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
    history_context = service._code_calc_history_context(storage)
    problem_id = generate_token("ccalc")

    generated = service.problem_generator.generate_code_calc_problem_sync(
        problem_id=problem_id,
        track_id=track_id,
        language_id=language_id,
        difficulty=difficulty_choices[difficulty_id]["generator"],
        mode="code-calc",
        history_context=history_context,
    )

    storage.append(
        {
            "type": "code_calc_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "difficulty": difficulty_id,
            "title": generated["title"],
            "code": generated["code"],
            "expected_output": generated["expected_output"],
            "explanation": generated["explanation"],
            "created_at": utcnow(),
        }
    )

    return {
        "problemId": problem_id,
        "title": generated["title"],
        "code": generated["code"],
        "language": language_id,
    }


def submit_code_calc_answer(
    service: Any,
    username: str,
    problem_id: str,
    output_text: str,
    *,
    utcnow: Callable[[], str],
) -> Dict[str, Any]:
    storage = service._get_user_storage(username)
    instance = storage.find_one(
        lambda item: item.get("type") == "code_calc_instance" and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError("해당 코드 계산 문제를 찾지 못했습니다.")

    expected_output = (instance.get("expected_output") or "").strip()
    user_output = (output_text or "").strip()
    is_correct = expected_output == user_output

    storage.append(
        {
            "type": "code_calc_event",
            "problem_id": problem_id,
            "language": instance.get("language"),
            "difficulty": instance.get("difficulty"),
            "submitted_output": user_output,
            "expected_output": expected_output,
            "correct": is_correct,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    return {
        "correct": is_correct,
        "expected_output": expected_output,
        "explanation": instance.get("explanation"),
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

    storage.append(
        {
            "type": "code_error_event",
            "problem_id": problem_id,
            "language": instance.get("language"),
            "difficulty": instance.get("difficulty"),
            "selected_index": selected_idx,
            "correct_index": correct_idx,
            "correct": is_correct,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

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
    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("리포트를 입력해주세요.")
    if len(normalized_report) > 12000:
        raise ValueError("리포트 길이는 12000자를 초과할 수 없습니다.")

    storage = service._get_user_storage(username)
    instance = storage.find_one(
        lambda item: item.get("type") == "auditor_instance" and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError("해당 감사관 문제를 찾지 못했습니다.")

    evaluation = service.ai_client.analyze_auditor_report(
        code=str(instance.get("code") or ""),
        prompt=str(instance.get("prompt") or ""),
        report=normalized_report,
        trap_catalog=instance.get("trap_catalog") or [],
        reference_report=str(instance.get("reference_report") or ""),
        language=str(instance.get("language") or ""),
        difficulty=str(instance.get("difficulty") or ""),
    )

    score_raw = evaluation.get("score")
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))

    is_passed = score >= AUDITOR_PASS_THRESHOLD
    verdict = "passed" if is_passed else "failed"

    feedback = {
        "summary": str(evaluation.get("summary") or ""),
        "strengths": evaluation.get("strengths") if isinstance(evaluation.get("strengths"), list) else [],
        "improvements": evaluation.get("improvements") if isinstance(evaluation.get("improvements"), list) else [],
    }
    found_types = evaluation.get("found_types") if isinstance(evaluation.get("found_types"), list) else []
    missed_types = evaluation.get("missed_types") if isinstance(evaluation.get("missed_types"), list) else []
    feedback_source = str(evaluation.get("feedback_source") or "fallback")
    ai_provider = str(evaluation.get("ai_provider") or "").strip() or None
    reference_report = str(instance.get("reference_report") or "")

    storage.append(
        {
            "type": "auditor_event",
            "problem_id": problem_id,
            "track": instance.get("track"),
            "language": instance.get("language"),
            "mode": "auditor",
            "difficulty": instance.get("difficulty"),
            "report": normalized_report,
            "score": score,
            "correct": is_passed,
            "verdict": verdict,
            "feedback": feedback,
            "feedback_source": feedback_source,
            "ai_provider": ai_provider,
            "found_types": found_types,
            "missed_types": missed_types,
            "reference_report": reference_report,
            "pass_threshold": AUDITOR_PASS_THRESHOLD,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    return {
        "correct": is_passed,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "feedbackSource": feedback_source,
        "aiProvider": ai_provider,
        "foundTypes": found_types,
        "missedTypes": missed_types,
        "referenceReport": reference_report,
        "passThreshold": int(AUDITOR_PASS_THRESHOLD),
    }


def request_single_file_analysis_problem(
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
    history_context = service._single_file_analysis_history_context(storage)
    problem_id = generate_token("sfile")

    generated = service.problem_generator.generate_single_file_analysis_problem_sync(
        problem_id=problem_id,
        track_id=track_id,
        language_id=language_id,
        difficulty=difficulty_choices[difficulty_id]["generator"],
        mode="single-file-analysis",
        history_context=history_context,
    )

    files = _normalize_advanced_analysis_files(
        generated.get("files"),
        min_count=1,
        max_count=1,
        default_language=language_id,
        default_role="entrypoint",
    )
    checklist = _normalize_str_list(generated.get("checklist"))[:4]
    summary = str(generated.get("summary") or "").strip()
    prompt = str(generated.get("prompt") or "").strip()
    workspace = str(generated.get("workspace") or "").strip() or "single-file-analysis.workspace"
    reference_report = str(generated.get("reference_report") or "").strip()

    storage.append(
        {
            "type": "single_file_analysis_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": "single-file-analysis",
            "difficulty": difficulty_id,
            "title": generated.get("title"),
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
        "title": generated.get("title") or "단일 파일 분석 문제",
        "mode": "single-file-analysis",
        "summary": summary,
        "language": language_id,
        "difficulty": difficulty_id,
        "workspace": workspace,
        "files": files,
        "prompt": prompt,
        "checklist": checklist,
    }


def request_multi_file_analysis_problem(
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
    history_context = service._multi_file_analysis_history_context(storage)
    problem_id = generate_token("mfile")

    generated = service.problem_generator.generate_multi_file_analysis_problem_sync(
        problem_id=problem_id,
        track_id=track_id,
        language_id=language_id,
        difficulty=difficulty_choices[difficulty_id]["generator"],
        mode="multi-file-analysis",
        history_context=history_context,
    )

    files = _normalize_advanced_analysis_files(
        generated.get("files"),
        min_count=2,
        max_count=6,
        default_language=language_id,
        default_role="module",
    )
    checklist = _normalize_str_list(generated.get("checklist"))[:5]
    summary = str(generated.get("summary") or "").strip()
    prompt = str(generated.get("prompt") or "").strip()
    workspace = str(generated.get("workspace") or "").strip() or "multi-file-analysis.workspace"
    reference_report = str(generated.get("reference_report") or "").strip()

    storage.append(
        {
            "type": "multi_file_analysis_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": "multi-file-analysis",
            "difficulty": difficulty_id,
            "title": generated.get("title"),
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
        "title": generated.get("title") or "다중 파일 분석 문제",
        "mode": "multi-file-analysis",
        "summary": summary,
        "language": language_id,
        "difficulty": difficulty_id,
        "workspace": workspace,
        "files": files,
        "prompt": prompt,
        "checklist": checklist,
    }


def request_fullstack_analysis_problem(
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
    history_context = service._fullstack_analysis_history_context(storage)
    problem_id = generate_token("fstack")

    generated = service.problem_generator.generate_fullstack_analysis_problem_sync(
        problem_id=problem_id,
        track_id=track_id,
        language_id=language_id,
        difficulty=difficulty_choices[difficulty_id]["generator"],
        mode="fullstack-analysis",
        history_context=history_context,
    )

    files = _normalize_advanced_analysis_files(
        generated.get("files"),
        min_count=3,
        max_count=8,
        default_language=language_id,
        default_role="backend",
    )
    checklist = _normalize_str_list(generated.get("checklist"))[:5]
    summary = str(generated.get("summary") or "").strip()
    prompt = str(generated.get("prompt") or "").strip()
    workspace = str(generated.get("workspace") or "").strip() or "fullstack-analysis.workspace"
    reference_report = str(generated.get("reference_report") or "").strip()

    storage.append(
        {
            "type": "fullstack_analysis_instance",
            "problem_id": problem_id,
            "track": track_id,
            "language": language_id,
            "mode": "fullstack-analysis",
            "difficulty": difficulty_id,
            "title": generated.get("title"),
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
        "title": generated.get("title") or "풀스택 코드 분석 문제",
        "mode": "fullstack-analysis",
        "summary": summary,
        "language": language_id,
        "difficulty": difficulty_id,
        "workspace": workspace,
        "files": files,
        "prompt": prompt,
        "checklist": checklist,
    }


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
    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("리포트를 입력해주세요.")
    if len(normalized_report) > 12000:
        raise ValueError("리포트 길이는 12000자를 초과할 수 없습니다.")

    storage = service._get_user_storage(username)
    instance = storage.find_one(
        lambda item: item.get("type") == instance_type and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError(missing_problem_message)

    files = _normalize_advanced_analysis_files(
        instance.get("files"),
        min_count=1,
        max_count=8,
        default_language=str(instance.get("language") or "python"),
        default_role="module",
    )
    reference_report = str(instance.get("reference_report") or "").strip()
    checklist = _normalize_str_list(instance.get("checklist"))[:5]
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
        evaluation = {
            "summary": "AI 채점 중 오류가 발생해 기본 실패 응답을 반환했습니다. 잠시 후 다시 시도해주세요.",
            "strengths": [],
            "improvements": ["리포트 내용을 유지한 채 재시도해주세요."],
            "score": 0.0,
            "correct": False,
            "error_detail": str(exc),
        }

    score_raw = evaluation.get("score") if isinstance(evaluation, dict) else 0.0
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))

    is_passed = score >= ADVANCED_ANALYSIS_PASS_THRESHOLD
    verdict = "passed" if is_passed else "failed"
    feedback = {
        "summary": str((evaluation or {}).get("summary") or ""),
        "strengths": _normalize_str_list((evaluation or {}).get("strengths")),
        "improvements": _normalize_str_list((evaluation or {}).get("improvements")),
    }
    analysis_error_detail = str((evaluation or {}).get("error_detail") or "")
    feedback_source = str((evaluation or {}).get("feedback_source") or "fallback")
    ai_provider = str((evaluation or {}).get("ai_provider") or "").strip() or None

    storage.append(
        {
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
            "pass_threshold": ADVANCED_ANALYSIS_PASS_THRESHOLD,
            "analysis_error_detail": analysis_error_detail,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    return {
        "correct": is_passed,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "feedbackSource": feedback_source,
        "aiProvider": ai_provider,
        "referenceReport": reference_report,
        "passThreshold": int(ADVANCED_ANALYSIS_PASS_THRESHOLD),
    }


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
    inference_type = select_context_inference_type(difficulty_id)
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

    expected_facets = _normalize_str_list(generated.get("expected_facets"))
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
    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("리포트를 입력해주세요.")
    if len(normalized_report) > 12000:
        raise ValueError("리포트 길이는 12000자를 초과할 수 없습니다.")

    storage = service._get_user_storage(username)
    instance = storage.find_one(
        lambda item: item.get("type") == "context_inference_instance" and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError("problemId가 올바르지 않습니다.")

    expected_facets = _normalize_str_list(instance.get("expected_facets"))
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
        evaluation = {
            "summary": "AI 채점 중 오류가 발생해 기본 실패 응답을 반환했습니다. 잠시 후 다시 시도해주세요.",
            "strengths": [],
            "improvements": ["리포트 내용을 유지한 채 재시도해주세요."],
            "score": 0.0,
            "correct": False,
            "found_types": [],
            "missed_types": expected_facets,
            "error_detail": str(exc),
        }

    score_raw = evaluation.get("score") if isinstance(evaluation, dict) else 0.0
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))

    is_passed = score >= CONTEXT_INFERENCE_PASS_THRESHOLD
    verdict = "passed" if is_passed else "failed"

    feedback = {
        "summary": str((evaluation or {}).get("summary") or ""),
        "strengths": _normalize_str_list((evaluation or {}).get("strengths")),
        "improvements": _normalize_str_list((evaluation or {}).get("improvements")),
    }
    found_types = _normalize_str_list((evaluation or {}).get("found_types"))
    missed_types = _normalize_str_list((evaluation or {}).get("missed_types"))
    analysis_error_detail = str((evaluation or {}).get("error_detail") or "")
    feedback_source = str((evaluation or {}).get("feedback_source") or "fallback")
    ai_provider = str((evaluation or {}).get("ai_provider") or "").strip() or None

    storage.append(
        {
            "type": "context_inference_event",
            "problem_id": problem_id,
            "track": instance.get("track"),
            "language": instance.get("language"),
            "mode": "context-inference",
            "difficulty": instance.get("difficulty"),
            "inference_type": inference_type,
            "report": normalized_report,
            "score": score,
            "correct": is_passed,
            "verdict": verdict,
            "feedback": feedback,
            "feedback_source": feedback_source,
            "ai_provider": ai_provider,
            "found_types": found_types,
            "missed_types": missed_types,
            "reference_report": reference_report,
            "pass_threshold": CONTEXT_INFERENCE_PASS_THRESHOLD,
            "analysis_error_detail": analysis_error_detail,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    return {
        "correct": is_passed,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "feedbackSource": feedback_source,
        "aiProvider": ai_provider,
        "foundTypes": found_types,
        "missedTypes": missed_types,
        "referenceReport": reference_report,
        "passThreshold": int(CONTEXT_INFERENCE_PASS_THRESHOLD),
    }


def request_refactoring_choice_problem(
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
        )
    except Exception as exc:  # pragma: no cover - network dependent path
        raise ValueError("최적의 선택 문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    title = str(generated.get("title") or "").strip() or "최적의 선택 문제"
    scenario = str(generated.get("scenario") or "").strip()
    prompt = str(generated.get("prompt") or "").strip() or "A/B/C 중 가장 적합한 코드를 선택하고 근거를 작성하세요."

    constraints = _normalize_str_list(generated.get("constraints"))
    if len(constraints) > constraint_count:
        constraints = constraints[:constraint_count]
    while len(constraints) < constraint_count:
        constraints.append(f"제약 조건 {len(constraints) + 1}")

    options = _normalize_refactoring_choice_options(generated.get("options"))
    decision_facets = _normalize_refactoring_choice_facets(generated.get("decision_facets"))

    best_option = str(generated.get("best_option") or "A").strip().upper()
    if best_option not in REFACTORING_CHOICE_OPTION_IDS:
        best_option = "A"

    option_reviews = _normalize_refactoring_choice_option_reviews(generated.get("option_reviews"))
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
    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("리포트를 입력해주세요.")
    if len(normalized_report) > 12000:
        raise ValueError("리포트 길이는 12000자를 초과할 수 없습니다.")

    normalized_selected_option = str(selected_option or "").strip().upper()
    if normalized_selected_option not in REFACTORING_CHOICE_OPTION_IDS:
        raise ValueError("selectedOption은 A, B, C 중 하나여야 합니다.")

    storage = service._get_user_storage(username)
    instance = storage.find_one(
        lambda item: item.get("type") == "refactoring_choice_instance" and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError("problemId가 올바르지 않습니다.")

    decision_facets = _normalize_refactoring_choice_facets(instance.get("decision_facets"))
    constraints = _normalize_str_list(instance.get("constraints"))
    options = _normalize_refactoring_choice_options(instance.get("options"))
    best_option = str(instance.get("best_option") or "A").strip().upper()
    if best_option not in REFACTORING_CHOICE_OPTION_IDS:
        best_option = "A"
    option_reviews = _normalize_refactoring_choice_option_reviews(instance.get("option_reviews"))
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
        evaluation = {
            "summary": "AI 채점 중 오류가 발생해 기본 실패 응답을 반환했습니다. 잠시 후 다시 시도해주세요.",
            "strengths": [],
            "improvements": ["리포트 내용을 유지한 채 재시도해주세요."],
            "score": 0.0,
            "correct": False,
            "found_types": [],
            "missed_types": decision_facets,
            "error_detail": str(exc),
        }

    score_raw = evaluation.get("score") if isinstance(evaluation, dict) else 0.0
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))

    is_passed = score >= REFACTORING_CHOICE_PASS_THRESHOLD
    verdict = "passed" if is_passed else "failed"

    feedback = {
        "summary": str((evaluation or {}).get("summary") or ""),
        "strengths": _normalize_str_list((evaluation or {}).get("strengths")),
        "improvements": _normalize_str_list((evaluation or {}).get("improvements")),
    }

    expected_set = set(decision_facets)
    found_types: list[str] = []
    for token in _normalize_str_list((evaluation or {}).get("found_types")):
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
    analysis_error_detail = str((evaluation or {}).get("error_detail") or "")
    feedback_source = str((evaluation or {}).get("feedback_source") or "fallback")
    ai_provider = str((evaluation or {}).get("ai_provider") or "").strip() or None

    storage.append(
        {
            "type": "refactoring_choice_event",
            "problem_id": problem_id,
            "track": instance.get("track"),
            "language": instance.get("language"),
            "mode": "refactoring-choice",
            "difficulty": instance.get("difficulty"),
            "selected_option": normalized_selected_option,
            "best_option": best_option,
            "report": normalized_report,
            "score": score,
            "correct": is_passed,
            "verdict": verdict,
            "feedback": feedback,
            "feedback_source": feedback_source,
            "ai_provider": ai_provider,
            "found_types": found_types,
            "missed_types": missed_types,
            "reference_report": reference_report,
            "option_reviews": option_reviews,
            "pass_threshold": REFACTORING_CHOICE_PASS_THRESHOLD,
            "analysis_error_detail": analysis_error_detail,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    return {
        "correct": is_passed,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "feedbackSource": feedback_source,
        "aiProvider": ai_provider,
        "foundTypes": found_types,
        "missedTypes": missed_types,
        "referenceReport": reference_report,
        "passThreshold": int(REFACTORING_CHOICE_PASS_THRESHOLD),
        "selectedOption": normalized_selected_option,
        "bestOption": best_option,
        "optionReviews": option_reviews,
    }


def request_code_blame_problem(
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
    history_context = service._code_blame_history_context(storage)
    candidate_count = CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY.get(difficulty_id, 4)
    culprit_count = select_code_blame_culprit_count()
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
        )
    except Exception as exc:  # pragma: no cover - network dependent path
        raise ValueError("범인 찾기 문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc

    title = str(generated.get("title") or "").strip() or "범인 찾기 문제"
    prompt = str(generated.get("prompt") or "").strip() or "에러 로그와 diff를 비교해 범인 커밋을 추리하세요."
    error_log = str(generated.get("error_log") or "").rstrip()
    commits = _normalize_code_blame_commits(generated.get("commits"), candidate_count=candidate_count)
    option_ids = [row["optionId"] for row in commits]

    decision_facets = _normalize_code_blame_facets(generated.get("decision_facets"))
    culprit_commits = _normalize_code_blame_option_ids(generated.get("culprit_commits"), option_ids)
    if culprit_count == 1:
        culprit_commits = culprit_commits[:1]
    else:
        culprit_commits = culprit_commits[:2]

    if not culprit_commits:
        culprit_commits = option_ids[: min(culprit_count, len(option_ids))]
    if culprit_count == 2 and len(culprit_commits) < 2 and len(option_ids) >= 2:
        culprit_commits = option_ids[:2]

    commit_reviews = _normalize_code_blame_commit_reviews(generated.get("commit_reviews"), option_ids)
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
    normalized_report = (report or "").strip()
    if not normalized_report:
        raise ValueError("리포트를 입력해주세요.")
    if len(normalized_report) > 12000:
        raise ValueError("리포트 길이는 12000자를 초과할 수 없습니다.")

    storage = service._get_user_storage(username)
    instance = storage.find_one(
        lambda item: item.get("type") == "code_blame_instance" and item.get("problem_id") == problem_id
    )
    if not instance:
        raise ValueError("problemId가 올바르지 않습니다.")

    candidate_count = int(instance.get("candidate_count") or len(instance.get("commits") or []) or 3)
    commits = _normalize_code_blame_commits(instance.get("commits"), candidate_count=candidate_count)
    option_ids = [row["optionId"] for row in commits]
    normalized_selected_commits = _normalize_code_blame_option_ids(selected_commits, option_ids)
    if not normalized_selected_commits:
        raise ValueError("selectedCommits를 최소 1개 선택해야 합니다.")
    if len(normalized_selected_commits) > 2:
        raise ValueError("selectedCommits는 최대 2개까지 선택할 수 있습니다.")

    culprit_commits = _normalize_code_blame_option_ids(instance.get("culprit_commits"), option_ids)
    if not culprit_commits:
        culprit_commits = option_ids[:1]
    if len(culprit_commits) > 2:
        culprit_commits = culprit_commits[:2]

    decision_facets = _normalize_code_blame_facets(instance.get("decision_facets"))
    commit_reviews = _normalize_code_blame_commit_reviews(instance.get("commit_reviews"), option_ids)
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
        evaluation = {
            "summary": "AI 채점 중 오류가 발생해 기본 실패 응답을 반환했습니다. 잠시 후 다시 시도해주세요.",
            "strengths": [],
            "improvements": ["리포트 내용을 유지한 채 재시도해주세요."],
            "score": 0.0,
            "correct": False,
            "found_types": [],
            "missed_types": decision_facets,
            "error_detail": str(exc),
        }

    score_raw = evaluation.get("score") if isinstance(evaluation, dict) else 0.0
    try:
        score = float(score_raw) if score_raw is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))

    is_passed = score >= CODE_BLAME_PASS_THRESHOLD
    verdict = "passed" if is_passed else "failed"

    feedback = {
        "summary": str((evaluation or {}).get("summary") or ""),
        "strengths": _normalize_str_list((evaluation or {}).get("strengths")),
        "improvements": _normalize_str_list((evaluation or {}).get("improvements")),
    }

    expected_set = set(decision_facets)
    found_types: list[str] = []
    for token in _normalize_str_list((evaluation or {}).get("found_types")):
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
    analysis_error_detail = str((evaluation or {}).get("error_detail") or "")
    feedback_source = str((evaluation or {}).get("feedback_source") or "fallback")
    ai_provider = str((evaluation or {}).get("ai_provider") or "").strip() or None

    storage.append(
        {
            "type": "code_blame_event",
            "problem_id": problem_id,
            "track": instance.get("track"),
            "language": instance.get("language"),
            "mode": "code-blame",
            "difficulty": instance.get("difficulty"),
            "selected_commits": normalized_selected_commits,
            "culprit_commits": culprit_commits,
            "report": normalized_report,
            "score": score,
            "correct": is_passed,
            "verdict": verdict,
            "feedback": feedback,
            "feedback_source": feedback_source,
            "ai_provider": ai_provider,
            "found_types": found_types,
            "missed_types": missed_types,
            "reference_report": reference_report,
            "commit_reviews": commit_reviews,
            "pass_threshold": CODE_BLAME_PASS_THRESHOLD,
            "analysis_error_detail": analysis_error_detail,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    return {
        "correct": is_passed,
        "score": score,
        "verdict": verdict,
        "feedback": feedback,
        "feedbackSource": feedback_source,
        "aiProvider": ai_provider,
        "foundTypes": found_types,
        "missedTypes": missed_types,
        "referenceReport": reference_report,
        "passThreshold": int(CODE_BLAME_PASS_THRESHOLD),
        "selectedCommits": normalized_selected_commits,
        "culpritCommits": culprit_commits,
        "commitReviews": commit_reviews,
    }


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
        "skillLevel": profile.get("skill_level", "beginner"),
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

    storage.append(
        {
            "type": "code_arrange_event",
            "problem_id": problem_id,
            "language": instance.get("language"),
            "difficulty": instance.get("difficulty"),
            "submitted_order": order,
            "correct_order": correct_order,
            "correct": is_correct_overall,
            "created_at": utcnow(),
        }
    )
    service._update_tier_if_needed(storage, username)

    block_map = {blk["id"]: blk["code"] for blk in (instance.get("blocks") or [])}
    answer_code = "\n".join(block_map.get(block_id, "") for block_id in correct_order).strip()

    return {
        "correct": is_correct_overall,
        "results": results,
        "answerOrder": correct_order,
        "answerCode": answer_code,
    }

