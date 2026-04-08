from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.orm import Session, joinedload, selectinload

from server.db.models import (
    AIAnalysis,
    AnalysisType,
    Problem,
    ProblemContentStatus,
    ProblemDifficulty,
    ProblemKind,
    Submission,
    SubmissionStatus,
    User,
    UserProblemStat,
)
from server.db.session import SessionLocal
from server.features.jobs.queue import (
    enqueue_problem_follow_up_job,
    get_redis_connection,
    is_problem_follow_up_rq_enabled,
)
from server.features.learning.continuity import sync_review_queue_for_submission
from server.features.learning.catalog import infer_mode_from_problem, mode_from_problem_kind
from server.features.learning.ops_service import record_ops_event
from server.features.learning.problem_stat_service import classify_wrong_answer_type, update_user_problem_stat
from server.features.reports.pdf import get_latest_report_detail
from server.bootstrap import learning_service, storage_manager, user_service
from server.features.learning.content import normalize_language_id
from server.features.learning.reporting import trend_summary
from server.features.learning.skill_levels import DEFAULT_SKILL_LEVEL, normalize_skill_level

logger = logging.getLogger(__name__)


# Shared metadata and normalization

_HISTORY_TOTAL_CACHE_PREFIX = "platform:history:total:"

_PROBLEM_KIND_BY_MODE: dict[str, ProblemKind] = {
    "analysis": ProblemKind.analysis,
    "code-block": ProblemKind.code_block,
    "code-arrange": ProblemKind.code_arrange,
    "auditor": ProblemKind.auditor,
    "refactoring-choice": ProblemKind.refactoring_choice,
    "code-blame": ProblemKind.code_blame,
    "single-file-analysis": ProblemKind.analysis,
    "multi-file-analysis": ProblemKind.analysis,
    "fullstack-analysis": ProblemKind.analysis,
}

_PROBLEM_DIFFICULTY_BY_CLIENT: dict[str, ProblemDifficulty] = {
    "beginner": ProblemDifficulty.easy,
    "intermediate": ProblemDifficulty.medium,
    "advanced": ProblemDifficulty.hard,
    "easy": ProblemDifficulty.easy,
    "medium": ProblemDifficulty.medium,
    "hard": ProblemDifficulty.hard,
}

_ANALYSIS_TYPE_BY_MODE: dict[str, AnalysisType] = {
    "analysis": AnalysisType.explain,
    "code-block": AnalysisType.explain,
    "code-arrange": AnalysisType.explain,
    "auditor": AnalysisType.review,
    "refactoring-choice": AnalysisType.review,
    "code-blame": AnalysisType.review,
    "single-file-analysis": AnalysisType.review,
    "multi-file-analysis": AnalysisType.review,
    "fullstack-analysis": AnalysisType.review,
}

_EVENT_TYPE_BY_MODE: dict[str, str] = {
    "analysis": "learning_event",
    "code-block": "learning_event",
    "code-arrange": "code_arrange_event",
    "auditor": "auditor_event",
    "refactoring-choice": "refactoring_choice_event",
    "code-blame": "code_blame_event",
    "single-file-analysis": "single_file_analysis_event",
    "multi-file-analysis": "multi_file_analysis_event",
    "fullstack-analysis": "fullstack_analysis_event",
}

def _normalize_skill_level_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    source = normalized.get("skillLevel")
    if source in (None, ""):
        source = normalized.get("skill_level")
    if source not in (None, ""):
        normalized_level = normalize_skill_level(source, DEFAULT_SKILL_LEVEL)
        normalized["skillLevel"] = normalized_level
        if "skill_level" in normalized:
            normalized["skill_level"] = normalized_level
    return normalized

def _normalize_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in _PROBLEM_KIND_BY_MODE:
        raise ValueError(f"unsupported mode: {mode}")
    return normalized

def _canonical_problem_payload(
    mode: str,
    payload: dict[str, Any],
    *,
    language: str,
    difficulty: str,
) -> dict[str, Any]:
    normalized_payload = dict(payload)
    legacy_problem = payload.get("problem") if mode == "analysis" else None
    canonical_problem = dict(legacy_problem) if isinstance(legacy_problem, dict) else {}
    canonical_payload = (
        {**canonical_problem, **{key: value for key, value in normalized_payload.items() if key != "problem"}}
        if canonical_problem
        else normalized_payload
    )

    problem_id = str(
        canonical_payload.get("problemId")
        or canonical_problem.get("problemId")
        or canonical_problem.get("id")
        or normalized_payload.get("problemId")
        or normalized_payload.get("id")
        or ""
    ).strip()
    if problem_id:
        canonical_payload["problemId"] = problem_id
    canonical_payload.pop("id", None)
    canonical_payload["mode"] = mode
    if not str(canonical_payload.get("language") or "").strip():
        canonical_payload["language"] = language
    if not str(canonical_payload.get("difficulty") or "").strip():
        canonical_payload["difficulty"] = difficulty
    return _normalize_skill_level_payload(canonical_payload)

def _response_problem_payload(mode: str, payload: dict[str, Any]) -> dict[str, Any]:
    if mode != "analysis":
        return payload

    legacy_problem = dict(payload)
    problem_id = str(legacy_problem.get("problemId") or "").strip()
    if problem_id:
        legacy_problem.setdefault("id", problem_id)
    return {
        **payload,
        "problem": legacy_problem,
    }


# Follow-up settings

class ProblemFollowUpUnavailableError(RuntimeError):
    """Raised when follow-up persistence cannot be reserved before streaming."""

def _get_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if not raw:
        return max(default, minimum)
    try:
        return max(int(raw), minimum)
    except (TypeError, ValueError):
        return max(default, minimum)

_PROBLEM_FOLLOW_UP_WORKERS = _get_int_env("CODE_PLATFORM_PROBLEM_FOLLOW_UP_WORKERS", 8)

_PROBLEM_FOLLOW_UP_PENDING_MAX = _get_int_env(
    "CODE_PLATFORM_PROBLEM_FOLLOW_UP_PENDING_MAX",
    max(_PROBLEM_FOLLOW_UP_WORKERS * 8, 128),
    minimum=_PROBLEM_FOLLOW_UP_WORKERS,
)

_PROBLEM_FOLLOW_UP_EXECUTOR = ThreadPoolExecutor(
    max_workers=_PROBLEM_FOLLOW_UP_WORKERS,
    thread_name_prefix="problem-follow-up",
)

_PROBLEM_FOLLOW_UP_SLOTS = threading.BoundedSemaphore(_PROBLEM_FOLLOW_UP_PENDING_MAX)

_DEFAULT_HISTORY_LIMIT = max(int(os.getenv("CODE_PLATFORM_HISTORY_DEFAULT_LIMIT", "200") or "200"), 1)


# Runtime adapters

def list_public_languages() -> list[dict[str, str]]:
    return learning_service.list_languages()

def _load_runtime_history(username: str, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is None:
        return learning_service.user_history(username)
    try:
        return learning_service.user_history(username, limit=limit)
    except Exception:
        logger.exception(
            "platform_bridge_recent_history_load_failed username=%s limit=%s",
            username,
            limit,
        )
        return learning_service.user_history(username)

def _load_runtime_attempt_events(username: str) -> list[dict[str, Any]]:
    try:
        storage = storage_manager.get_storage(username)
    except Exception:
        logger.exception("platform_bridge_runtime_attempt_load_failed username=%s", username)
        return []
    try:
        return learning_service._collect_attempt_events(storage)
    except Exception:
        logger.exception("platform_bridge_runtime_attempt_collection_failed username=%s", username)
        return []

def _request_runtime_problem(
    mode: str,
    *,
    username: str,
    language: str,
    difficulty: str,
    on_text_delta: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if mode == "analysis":
        return learning_service.request_problem(username, language, difficulty, on_text_delta=on_text_delta)
    if mode == "code-block":
        return learning_service.request_code_block_problem(username, language, difficulty, on_text_delta=on_text_delta)
    if mode == "code-arrange":
        return learning_service.request_code_arrange_problem(username, language, difficulty)
    if mode == "auditor":
        return learning_service.request_auditor_problem(username, language, difficulty, on_text_delta=on_text_delta)
    if mode == "refactoring-choice":
        return learning_service.request_refactoring_choice_problem(
            username,
            language,
            difficulty,
            on_text_delta=on_text_delta,
        )
    if mode == "code-blame":
        return learning_service.request_code_blame_problem(username, language, difficulty, on_text_delta=on_text_delta)
    if mode == "single-file-analysis":
        return learning_service.request_single_file_analysis_problem(
            username,
            language,
            difficulty,
            on_text_delta=on_text_delta,
        )
    if mode == "multi-file-analysis":
        return learning_service.request_multi_file_analysis_problem(
            username,
            language,
            difficulty,
            on_text_delta=on_text_delta,
        )
    if mode == "fullstack-analysis":
        return learning_service.request_fullstack_analysis_problem(
            username,
            language,
            difficulty,
            on_text_delta=on_text_delta,
        )
    raise ValueError(f"unsupported mode: {mode}")

def _submit_runtime_answer(mode: str, *, username: str, body: dict[str, Any]) -> dict[str, Any]:
    if mode == "analysis":
        return learning_service.submit_explanation(
            username,
            str(body.get("languageId") or body.get("language") or "python"),
            str(body.get("problemId") or body.get("problem_id") or ""),
            str(body.get("explanation") or ""),
        )
    if mode == "code-block":
        return learning_service.submit_code_block_answer(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            int(body.get("selectedOption") if body.get("selectedOption") is not None else body.get("selected_option")),
        )
    if mode == "code-arrange":
        return learning_service.submit_code_arrange_answer(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            list(body.get("order") or []),
        )
    if mode == "auditor":
        return learning_service.submit_auditor_report(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            str(body.get("report") or ""),
        )
    if mode == "refactoring-choice":
        return learning_service.submit_refactoring_choice_report(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            str(body.get("selectedOption") or body.get("selected_option") or ""),
            str(body.get("report") or ""),
        )
    if mode == "code-blame":
        return learning_service.submit_code_blame_report(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            list(body.get("selectedCommits") or body.get("selected_commits") or []),
            str(body.get("report") or ""),
        )
    if mode == "single-file-analysis":
        return learning_service.submit_single_file_analysis_report(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            str(body.get("report") or ""),
        )
    if mode == "multi-file-analysis":
        return learning_service.submit_multi_file_analysis_report(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            str(body.get("report") or ""),
        )
    if mode == "fullstack-analysis":
        return learning_service.submit_fullstack_analysis_report(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            str(body.get("report") or ""),
        )
    raise ValueError(f"unsupported mode: {mode}")

@contextmanager
def _db_session(db: Session | None = None) -> Iterator[Session | None]:
    if db is not None and _supports_sql_session(db):
        yield db
        return

    if db is not None and not _supports_sql_session(db):
        yield None
        return

    with SessionLocal() as session:
        yield session

def _supports_sql_session(db: Any) -> bool:
    return all(hasattr(db, attr) for attr in ("add", "commit", "rollback", "query"))


# Persistence helpers

def _load_user_problem(session: Session, *, problem_id: str, user_id: int) -> Problem | None:
    normalized_problem_id = str(problem_id or "").strip()
    if not normalized_problem_id:
        return None

    problem: Problem | None = None
    try:
        problem = session.get(Problem, int(normalized_problem_id))
    except (AttributeError, TypeError, ValueError):
        problem = None

    if problem is None:
        query = getattr(session, "query", None)
        if callable(query):
            problem = query(Problem).filter(Problem.external_id == normalized_problem_id).first()

    if problem is None:
        return None

    created_by = getattr(problem, "created_by", None)
    if created_by is not None:
        try:
            if int(created_by) != int(user_id):
                return None
        except (TypeError, ValueError):
            return None

    return problem


def _problem_record_values(
    *,
    mode: str,
    user_id: int,
    problem_id: str,
    problem_payload: dict[str, Any],
    answer_payload: dict[str, Any] | list[Any] | None = None,
    existing_answer_payload: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    stored_answer_payload = existing_answer_payload
    if isinstance(answer_payload, (dict, list)) and answer_payload not in ({}, []):
        stored_answer_payload = answer_payload

    return {
        "external_id": problem_id,
        "kind": _PROBLEM_KIND_BY_MODE[mode],
        "title": _problem_title(problem_payload, mode),
        "description": _problem_description(problem_payload),
        "difficulty": _problem_difficulty(problem_payload),
        "language": _problem_language(problem_payload),
        "starter_code": _problem_starter_code(problem_payload),
        "problem_payload": dict(problem_payload),
        "answer_payload": stored_answer_payload,
        "options": _problem_options(problem_payload),
        "answer_index": _problem_answer_index(problem_payload),
        "reference_solution": _problem_reference_solution(problem_payload),
        "prompt_version": _problem_prompt_version(problem_payload, mode),
        "content_status": ProblemContentStatus.approved,
        "is_curated_sample": False,
        "is_published": False,
        "created_by": user_id,
    }


def _apply_problem_record_values(problem: Problem, values: dict[str, Any]) -> None:
    for field, value in values.items():
        setattr(problem, field, value)


def _bridge_payload(payload: dict[str, Any], bridge_id: str) -> dict[str, Any]:
    bridged = dict(payload)
    bridged["bridgeId"] = bridge_id
    bridged["source"] = "platform"
    return bridged


def _analysis_summary(result_payload: dict[str, Any]) -> str:
    feedback_summary = _feedback_summary(result_payload)
    if feedback_summary:
        return feedback_summary

    verdict = str(result_payload.get("verdict") or "").strip()
    if verdict:
        return verdict

    if result_payload.get("correct") is True:
        return "passed"
    if result_payload.get("correct") is False:
        return "failed"
    return "analysis"


def _persist_problem(
    *,
    mode: str,
    username: str,
    user_id: int,
    problem_payload: dict[str, Any],
    runtime_payload: dict[str, Any] | None = None,
    db: Session | None = None,
) -> None:
    problem_id = str(problem_payload.get("problemId") or "").strip()
    if not problem_id:
        return

    instance = dict(runtime_payload or {}) or _load_runtime_instance(username, problem_id)
    combined_payload = {**instance, **problem_payload}
    combined_payload.setdefault("mode", mode)

    with _db_session(db) as session:
        if session is None:
            return

        problem = _load_user_problem(
            session,
            problem_id=problem_id,
            user_id=user_id,
        )
        values = _problem_record_values(
            mode=mode,
            user_id=user_id,
            problem_id=problem_id,
            problem_payload=combined_payload,
            answer_payload=instance or None,
            existing_answer_payload=problem.answer_payload if problem is not None else None,
        )
        if problem is None:
            session.add(Problem(**values))
            return

        _apply_problem_record_values(problem, values)

def _persist_submission(
    *,
    mode: str,
    username: str,
    user_id: int,
    submission_payload: dict[str, Any],
    result_payload: dict[str, Any],
    db: Session | None = None,
) -> None:
    problem_id = str(submission_payload.get("problemId") or submission_payload.get("problem_id") or "").strip()
    if not problem_id:
        return

    bridge_id = f"submission-{uuid4().hex}"
    _mark_runtime_event(username=username, mode=mode, problem_id=problem_id, bridge_id=bridge_id)

    with _db_session(db) as session:
        if session is None:
            return

        problem = _load_user_problem(session, problem_id=problem_id, user_id=user_id)
        if problem is None:
            problem = _backfill_problem_from_runtime(
                session=session,
                mode=mode,
                username=username,
                user_id=user_id,
                problem_id=problem_id,
            )

        if problem is None:
            raise RuntimeError(f"platform_dual_write_failed: missing problem for {mode}:{problem_id}")

        stored_submission_payload = _bridge_payload(submission_payload, bridge_id)
        stored_result_payload = _bridge_payload(result_payload, bridge_id)

        submission = Submission(
            user_id=user_id,
            problem_id=problem.id,
            language=problem.language,
            code=_submission_code(mode, submission_payload),
            submission_payload=stored_submission_payload,
            status=_submission_status_from_result(result_payload),
            score=_submission_score(result_payload),
        )
        session.add(submission)
        session.flush()

        result_detail_json = json.dumps(stored_result_payload, ensure_ascii=False)

        session.add(
            AIAnalysis(
                user_id=user_id,
                submission_id=submission.id,
                analysis_type=_ANALYSIS_TYPE_BY_MODE[mode],
                result_summary=_analysis_summary(result_payload)[:1000],
                result_detail=result_detail_json[:10000],
                result_payload=stored_result_payload,
            )
        )

        update_user_problem_stat(
            db=session,
            user_id=user_id,
            problem_id=problem.id,
            score=submission.score,
            status=submission.status,
            analysis_summary=_feedback_summary(result_payload),
            analysis_detail=result_detail_json,
            increment_attempt=True,
        )
        session.flush()
        stat = session.get(UserProblemStat, (user_id, problem.id))
        wrong_payload = stat.wrong_answer_types if stat and isinstance(stat.wrong_answer_types, dict) else {}
        total_wrong = int(wrong_payload.get("total_wrong") or 0)
        wrong_type = wrong_payload.get("last_wrong_type")
        if not isinstance(wrong_type, str):
            wrong_type = classify_wrong_answer_type(
                submission.status,
                analysis_summary=_feedback_summary(result_payload),
                analysis_detail=result_detail_json,
            )
        sync_review_queue_for_submission(
            db=session,
            user_id=user_id,
            problem=problem,
            submission=submission,
            mode=mode,
            result_payload=result_payload,
            wrong_type=wrong_type,
            total_wrong=total_wrong,
        )

def _backfill_problem_from_runtime(
    *,
    session: Session,
    mode: str,
    username: str,
    user_id: int,
    problem_id: str,
) -> Problem | None:
    instance = _load_runtime_instance(username, problem_id)
    if not instance:
        return None

    combined_payload = {"problemId": problem_id, **instance}
    combined_payload.setdefault("mode", mode)
    problem = Problem(
        **_problem_record_values(
            mode=mode,
            user_id=user_id,
            problem_id=problem_id,
            problem_payload=combined_payload,
            answer_payload=instance,
        )
    )
    session.add(problem)
    session.flush()
    return problem

def _load_runtime_instance(username: str, problem_id: str) -> dict[str, Any]:
    try:
        storage = learning_service._get_user_storage(username)
        return learning_service._instances_by_id(storage).get(problem_id) or {}
    except Exception:
        logger.exception("platform_bridge_failed_to_load_runtime_instance username=%s problem_id=%s", username, problem_id)
        return {}

def _problem_title(payload: dict[str, Any], mode: str) -> str:
    title = str(payload.get("title") or "").strip()
    if title:
        return title[:200]
    fallback = {
        "analysis": "코드 분석 문제",
        "code-block": "코드 블록 문제",
        "code-arrange": "코드 배치 문제",
        "code-error": "코드 오류 문제",
        "auditor": "감사관 문제",
        "context-inference": "맥락 추론 문제",
        "refactoring-choice": "최적의 선택 문제",
        "code-blame": "범인 찾기 문제",
    }
    return fallback.get(mode, "학습 문제")

def _problem_description(payload: dict[str, Any]) -> str:
    for candidate in (
        payload.get("prompt"),
        payload.get("scenario"),
        payload.get("description"),
        payload.get("title"),
        "학습 문제",
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return "학습 문제"

def _problem_prompt_version(payload: dict[str, Any], mode: str) -> str:
    for key in ("promptVersion", "prompt_version"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value[:80]
    return f"{mode}-runtime-v1"[:80]

def _problem_language(payload: dict[str, Any]) -> str:
    return normalize_language_id(payload.get("language") or payload.get("languageId")) or "python"

def _problem_difficulty(payload: dict[str, Any]) -> ProblemDifficulty:
    raw = str(payload.get("difficulty") or payload.get("difficultyId") or "beginner").strip().lower()
    return _PROBLEM_DIFFICULTY_BY_CLIENT.get(raw, ProblemDifficulty.medium)

def _problem_starter_code(payload: dict[str, Any]) -> str | None:
    for key in ("code", "snippet", "errorLog", "error_log"):
        text = str(payload.get(key) or "").rstrip()
        if text:
            return text

    files = payload.get("files")
    if isinstance(files, list):
        rendered: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("code") or "").rstrip()
            if not content:
                continue
            file_path = str(item.get("path") or item.get("name") or "").strip()
            if file_path:
                rendered.append(f"File: {file_path}\n{content}")
            else:
                rendered.append(content)
        if rendered:
            return "\n\n".join(rendered)

    blocks = payload.get("blocks")
    if isinstance(blocks, list):
        rendered: list[str] = []
        for block in blocks:
            if isinstance(block, dict):
                code = str(block.get("code") or "").rstrip()
                if code:
                    rendered.append(code)
            else:
                rendered.append(str(block).rstrip())
        if rendered:
            return "\n".join(rendered)

    commits = payload.get("commits")
    if isinstance(commits, list):
        rendered = [str(item.get("diff") or "").rstrip() for item in commits if isinstance(item, dict)]
        rendered = [item for item in rendered if item]
        if rendered:
            return "\n\n".join(rendered)
    return None

def _problem_options(payload: dict[str, Any]) -> dict | list | None:
    for key in ("options", "blocks", "commits"):
        value = payload.get(key)
        if isinstance(value, (list, dict)):
            return value
    return None

def _problem_answer_index(payload: dict[str, Any]) -> int | None:
    for key in ("answer_index", "answerIndex", "correct_answer_index", "correctAnswerIndex"):
        value = payload.get(key)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    return None

def _problem_reference_solution(payload: dict[str, Any]) -> str | None:
    for key in ("reference_report", "referenceReport", "reference_solution", "referenceSolution"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return None

def _history_problem_files(payload: dict[str, Any], *, fallback_language: str = "python") -> list[dict[str, str]]:
    files = payload.get("files")
    if not isinstance(files, list):
        return []

    normalized: list[dict[str, str]] = []
    resolved_language = normalize_language_id(fallback_language) or "python"
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or item.get("code") or "").replace("\r\n", "\n")
        if not content.strip():
            continue
        path = str(item.get("path") or item.get("name") or f"src/file_{index}.txt").strip() or f"src/file_{index}.txt"
        name = str(item.get("name") or path.rsplit("/", 1)[-1]).strip() or f"file_{index}.txt"
        language = str(item.get("language") or resolved_language).strip().lower() or resolved_language
        role = str(item.get("role") or "module").strip() or "module"
        file_id = str(item.get("id") or path or f"file-{index}").strip() or f"file-{index}"
        normalized.append(
            {
                "id": file_id,
                "path": path,
                "name": name,
                "language": language,
                "role": role,
                "content": content,
            }
        )
    return normalized

def _history_problem_checklist(payload: dict[str, Any]) -> list[str]:
    checklist = payload.get("checklist")
    if not isinstance(checklist, list):
        return []
    return [str(item or "").strip() for item in checklist if str(item or "").strip()]

def _submission_status_from_result(result_payload: dict[str, Any]) -> SubmissionStatus:
    if result_payload.get("correct") is True:
        return SubmissionStatus.passed
    if result_payload.get("correct") is False:
        return SubmissionStatus.failed
    verdict = str(result_payload.get("verdict") or "").strip().lower()
    if verdict == "passed":
        return SubmissionStatus.passed
    if verdict == "failed":
        return SubmissionStatus.failed
    return SubmissionStatus.error

def _submission_score(result_payload: dict[str, Any]) -> int | None:
    raw = result_payload.get("score")
    try:
        return int(round(float(raw))) if raw is not None else None
    except (TypeError, ValueError):
        return None

def _submission_code(mode: str, submission_payload: dict[str, Any]) -> str:
    if mode == "analysis":
        return str(submission_payload.get("explanation") or "")
    if mode == "code-block":
        return f"selected_option={submission_payload.get('selectedOption', submission_payload.get('selected_option'))}"
    if mode == "code-arrange":
        return json.dumps(submission_payload.get("order") or [], ensure_ascii=False)
    if mode == "code-error":
        return f"selected_index={submission_payload.get('selectedIndex', submission_payload.get('selected_index'))}"
    if mode in {
        "auditor",
        "context-inference",
        "refactoring-choice",
        "code-blame",
        "single-file-analysis",
        "multi-file-analysis",
        "fullstack-analysis",
    }:
        return str(submission_payload.get("report") or "")
    return json.dumps(submission_payload, ensure_ascii=False)

def _feedback_summary(result_payload: dict[str, Any]) -> str:
    feedback = result_payload.get("feedback")
    if isinstance(feedback, dict):
        return str(feedback.get("summary") or "").strip()
    return ""

def _mark_runtime_event(*, username: str, mode: str, problem_id: str, bridge_id: str) -> None:
    event_type = _EVENT_TYPE_BY_MODE[mode]
    try:
        storage = storage_manager.get_storage(username)
        records = storage.read_all()
    except Exception:
        logger.exception("platform_bridge_failed_to_open_jsonl username=%s", username)
        return

    match_index: int | None = None
    for index in range(len(records) - 1, -1, -1):
        item = records[index]
        if item.get("type") != event_type:
            continue
        if str(item.get("problem_id") or "").strip() != problem_id:
            continue
        if mode == "analysis" and str(item.get("mode") or "").strip().lower() == "code-block":
            continue
        if mode == "code-block" and str(item.get("mode") or "").strip().lower() != "code-block":
            continue
        if str(item.get("bridgeId") or "").strip():
            continue
        match_index = index
        break

    if match_index is None:
        return

    updated = dict(records[match_index])
    updated["bridgeId"] = bridge_id
    updated["source"] = "platform"
    records[match_index] = updated
    storage.write_all(records)

def _append_jsonl_record(username: str, record: dict[str, Any]) -> None:
    try:
        storage = storage_manager.get_storage(username)
    except FileNotFoundError:
        storage = storage_manager.create_user_storage(username)
    storage.append(record)


# History and reporting helpers

def _history_total_cache_key(username: str) -> str:
    return f"{_HISTORY_TOTAL_CACHE_PREFIX}{str(username or '').strip().lower()}"

def _history_cache_connection():
    try:
        return get_redis_connection()
    except Exception:
        logger.debug("platform_history_total_cache_unavailable", exc_info=True)
        return None

def _read_cached_public_history_total(username: str) -> int | None:
    conn = _history_cache_connection()
    if conn is None:
        return None
    try:
        raw = conn.get(_history_total_cache_key(username))
    except Exception:
        logger.debug("platform_history_total_cache_read_failed username=%s", username, exc_info=True)
        return None
    if raw in (None, b"", ""):
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    try:
        return max(int(str(raw).strip()), 0)
    except (TypeError, ValueError):
        return None

def _write_cached_public_history_total(username: str, total: int) -> None:
    conn = _history_cache_connection()
    if conn is None:
        return
    try:
        conn.set(_history_total_cache_key(username), str(max(int(total), 0)))
    except Exception:
        logger.debug("platform_history_total_cache_write_failed username=%s", username, exc_info=True)

def invalidate_public_history_total(username: str) -> None:
    conn = _history_cache_connection()
    if conn is None:
        return
    try:
        conn.delete(_history_total_cache_key(username))
    except Exception:
        logger.debug("platform_history_total_cache_invalidate_failed username=%s", username, exc_info=True)

def invalidate_public_history_total_for_user_id(db: Session, user_id: int) -> None:
    try:
        user = db.query(User).filter(User.id == user_id).first()
    except Exception:
        logger.debug(
            "platform_history_total_cache_user_lookup_failed user_id=%s",
            user_id,
            exc_info=True,
        )
        return
    username = str(getattr(user, "username", "") or "").strip()
    if username:
        invalidate_public_history_total(username)

def _history_bridge_ids(items: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("bridgeId") or item.get("bridge_id") or "").strip()
        for item in items
        if str(item.get("bridgeId") or item.get("bridge_id") or "").strip()
    }

def _count_db_history(*, username: str, seen_bridge_ids: set[str]) -> int:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        if user is None:
            return 0

        rows = (
            session.query(Submission)
            .join(Problem, Problem.id == Submission.problem_id)
            .filter(Submission.user_id == user.id)
            .all()
        )
        total = 0
        for submission in rows:
            payload = submission.submission_payload if isinstance(submission.submission_payload, dict) else {}
            bridge_id = str(payload.get("bridgeId") or "").strip()
            if bridge_id and bridge_id in seen_bridge_ids:
                continue
            total += 1
        return total

def _seed_public_history_total(username: str) -> int:
    runtime_events = _load_runtime_attempt_events(username)
    total = len(runtime_events) + _count_db_history(
        username=username,
        seen_bridge_ids=_history_bridge_ids(runtime_events),
    )
    _write_cached_public_history_total(username, total)
    return total

def get_public_me(current: User) -> dict[str, Any]:
    try:
        info = user_service.get_user_info(current.username)
    except FileNotFoundError:
        info = {
            "username": current.username,
            "display_name": current.username,
            "email": getattr(current, "email", None),
            "guest": False,
            "provider": None,
        }
    return {
        "id": current.id,
        "email": info.get("email") or current.email,
        "username": current.username,
        "role": current.role.value if hasattr(current.role, "value") else str(current.role),
        "status": current.status.value if hasattr(current.status, "value") else str(current.status),
        "display_name": info.get("display_name") or current.username,
        "displayName": info.get("display_name") or current.username,
        "guest": bool(info.get("guest")),
        "provider": info.get("provider"),
    }

def _normalize_history_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    try:
        return max(int(limit), 1)
    except (TypeError, ValueError):
        return _DEFAULT_HISTORY_LIMIT

def _count_public_history(username: str) -> int:
    runtime_events = _load_runtime_attempt_events(username)
    return len(runtime_events) + _count_db_history(
        username=username,
        seen_bridge_ids=_history_bridge_ids(runtime_events),
    )

def _submission_row_is_correct(submission: Submission) -> bool:
    if submission.status == SubmissionStatus.passed:
        return True
    payload = submission.result_payload if isinstance(submission.result_payload, dict) else {}
    return payload.get("correct") is True

def _summarize_db_history(*, username: str, seen_bridge_ids: set[str]) -> tuple[int, int]:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        if user is None:
            return 0, 0

        rows = (
            session.query(Submission)
            .join(Problem, Problem.id == Submission.problem_id)
            .filter(Submission.user_id == user.id)
            .all()
        )
        total = 0
        correct = 0
        for submission in rows:
            payload = submission.submission_payload if isinstance(submission.submission_payload, dict) else {}
            bridge_id = str(payload.get("bridgeId") or "").strip()
            if bridge_id and bridge_id in seen_bridge_ids:
                continue
            total += 1
            if _submission_row_is_correct(submission):
                correct += 1
        return total, correct

def get_public_memory(username: str) -> list[dict[str, Any]]:
    return learning_service.user_memory(username)

def _build_metric_snapshot(history: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = len(history)
    correct_count = sum(1 for item in history if item.get("correct") is True)
    accuracy = round((correct_count / attempts) * 100, 1) if attempts else None

    scores: list[float] = []
    for item in history:
        try:
            if item.get("score") is not None:
                scores.append(float(item.get("score")))
        except (TypeError, ValueError):
            continue
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    recent_accuracy = _window_accuracy(history[:5])
    previous_accuracy = _window_accuracy(history[5:10])
    return {
        "attempts": attempts,
        "accuracy": accuracy,
        "avgScore": avg_score,
        "trend": trend_summary(recent_accuracy, previous_accuracy),
    }

def _window_accuracy(history: list[dict[str, Any]]) -> float | None:
    if not history:
        return None
    correct = sum(1 for item in history if item.get("correct") is True)
    return round((correct / len(history)) * 100, 1)

def _load_db_history(*, username: str, seen_bridge_ids: set[str], limit: int | None = None) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        if user is None:
            return []

        query = (
            session.query(Submission)
            .options(joinedload(Submission.problem), selectinload(Submission.analyses))
            .join(Problem, Problem.id == Submission.problem_id)
            .filter(Submission.user_id == user.id)
            .order_by(Submission.id.desc())
        )
        if limit is not None:
            query = query.limit(max(limit * 3, 100))
        rows = query.all()
        items: list[dict[str, Any]] = []
        for submission in rows:
            payload = submission.submission_payload if isinstance(submission.submission_payload, dict) else {}
            bridge_id = str(payload.get("bridgeId") or "").strip()
            if bridge_id and bridge_id in seen_bridge_ids:
                continue

            problem = submission.problem
            if problem is None:
                continue

            problem_payload = problem.problem_payload if isinstance(problem.problem_payload, dict) else {}
            answer_payload = problem.answer_payload if isinstance(problem.answer_payload, dict) else {}
            analysis = _latest_submission_analysis(submission.analyses or [])
            result_payload = analysis.result_payload if analysis and isinstance(analysis.result_payload, dict) else {}
            mode = _history_mode_for_problem(problem=problem, problem_payload=problem_payload, answer_payload=answer_payload)
            item = _base_history_item(
                problem=problem,
                mode=mode,
                bridge_id=bridge_id,
                submission=submission,
                submission_payload=payload,
                problem_payload=problem_payload,
                result_payload=result_payload,
            )
            _apply_history_mode_fields(
                item,
                mode=mode,
                submission_payload=payload,
                problem_payload=problem_payload,
                result_payload=result_payload,
                problem=problem,
            )
            items.append(item)
            if limit is not None and len(items) >= limit:
                break
        return items[:limit] if limit is not None else items

def _history_mode_for_problem(
    *,
    problem: Problem,
    problem_payload: dict[str, Any],
    answer_payload: dict[str, Any] | None = None,
) -> str:
    return infer_mode_from_problem(
        problem=problem,
        problem_payload=problem_payload,
        answer_payload=answer_payload,
    )

def _mode_from_problem_kind(kind: Any) -> str:
    return mode_from_problem_kind(kind)

def _db_history_explanation(mode: str, submission: Submission, payload: dict[str, Any]) -> str | None:
    if mode == "analysis":
        return submission.code or None
    if mode == "code-block":
        selected = payload.get("selectedOption") or payload.get("selected_option")
        if selected is None:
            return None
        return f"선택: {selected}"
    if mode == "code-calc":
        return f"제출 출력: {submission.code}" if submission.code else None
    return submission.code or None

def _latest_submission_analysis(analyses: list[AIAnalysis] | tuple[AIAnalysis, ...]) -> AIAnalysis | None:
    if not analyses:
        return None

    def _analysis_sort_key(item: AIAnalysis) -> tuple[datetime, int]:
        created_at = getattr(item, "created_at", None)
        if not isinstance(created_at, datetime):
            created_at = datetime.min
        try:
            analysis_id = int(getattr(item, "id", 0) or 0)
        except (TypeError, ValueError):
            analysis_id = 0
        return created_at, analysis_id

    return max(analyses, key=_analysis_sort_key)


# Follow-up execution

def _record_ops_event_best_effort(**kwargs: Any) -> None:
    try:
        with _db_session(kwargs.pop("db", None)) as session:
            if session is None:
                return
            try:
                record_ops_event(session, **kwargs)
                session.commit()
            except Exception:
                session.rollback()
                raise
    except Exception:
        logger.exception("platform_bridge_failed_to_record_ops_event")

def _start_detached_task(target: Callable[[], None], *, name: str) -> None:
    thread = threading.Thread(target=target, name=name, daemon=True)
    thread.start()

def _perform_problem_follow_up(**kwargs: Any) -> None:
    persistence_kwargs = {
        "mode": kwargs["mode"],
        "username": kwargs["username"],
        "user_id": kwargs["user_id"],
        "problem_payload": kwargs["problem_payload"],
        "runtime_payload": kwargs.get("runtime_payload"),
    }
    with SessionLocal() as session:
        try:
            _persist_problem(db=session, **persistence_kwargs)
            session.commit()
        except Exception:
            session.rollback()
            raise
    _record_ops_event_best_effort(
        user_id=kwargs["user_id"],
        event_type=kwargs["event_type"],
        mode=kwargs["mode"],
        status="success",
        latency_ms=kwargs["latency_ms"],
        payload={"language": kwargs["language"], "difficulty": kwargs["difficulty"]},
    )

def run_problem_follow_up_background(**kwargs: Any) -> None:
    _perform_problem_follow_up(**kwargs)

def _run_problem_follow_up_best_effort(**kwargs: Any) -> None:
    try:
        _perform_problem_follow_up(**kwargs)
    except Exception:
        logger.exception("platform_bridge_problem_follow_up_failed")

def _defer_problem_follow_up(*, allow_rq: bool = True, **kwargs: Any) -> Future[None] | None:
    if allow_rq and is_problem_follow_up_rq_enabled():
        try:
            enqueue_problem_follow_up_job(**kwargs)
        except Exception as exc:
            raise ProblemFollowUpUnavailableError("stream_capacity_exceeded") from exc
        return None
    if not _PROBLEM_FOLLOW_UP_SLOTS.acquire(blocking=False):
        raise ProblemFollowUpUnavailableError("stream_capacity_exceeded")

    def _run_and_release() -> None:
        try:
            _perform_problem_follow_up(**kwargs)
        finally:
            _PROBLEM_FOLLOW_UP_SLOTS.release()

    try:
        return _PROBLEM_FOLLOW_UP_EXECUTOR.submit(_run_and_release)
    except RuntimeError:
        completed: Future[None] = Future()
        _run_and_release()
        completed.set_result(None)
        return completed

def _defer_failure_ops_event(*, user_id: int, mode: str, latency_ms: int, language: str, difficulty: str) -> None:
    try:
        _PROBLEM_FOLLOW_UP_EXECUTOR.submit(
            _record_ops_event_best_effort,
            user_id=user_id,
            event_type="problem_requested",
            mode=mode,
            status="failure",
            latency_ms=latency_ms,
            payload={"language": language, "difficulty": difficulty},
        )
    except RuntimeError:
        _start_detached_task(
            lambda: _record_ops_event_best_effort(
                user_id=user_id,
                event_type="problem_requested",
                mode=mode,
                status="failure",
                latency_ms=latency_ms,
                payload={"language": language, "difficulty": difficulty},
            ),
            name=f"problem-failure-event-{mode}",
        )


# Public bridge API

def _load_public_history(username: str, limit: int | None = None) -> tuple[list[dict[str, Any]], int | None]:
    effective_limit = _normalize_history_limit(limit)
    history_rows = _load_runtime_history(username, effective_limit)
    if effective_limit is not None:
        history_rows = history_rows[:effective_limit]
    seen_bridge_ids = _history_bridge_ids(history_rows)
    db_history = _load_db_history(username=username, seen_bridge_ids=seen_bridge_ids, limit=effective_limit)
    merged = history_rows + db_history
    merged.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    if effective_limit is not None:
        merged = merged[:effective_limit]
    return merged, effective_limit

def get_public_history(username: str, limit: int | None = None) -> list[dict[str, Any]]:
    history_rows, _ = _load_public_history(username, limit=limit)
    return history_rows

def _get_public_history_total(username: str) -> int:
    cached = _read_cached_public_history_total(username)
    if cached is not None:
        return cached
    return _seed_public_history_total(username)

def _increment_public_history_total(username: str, delta: int = 1) -> None:
    conn = _history_cache_connection()
    if conn is None:
        return
    key = _history_total_cache_key(username)
    try:
        if conn.exists(key):
            conn.incrby(key, int(delta))
            return
    except Exception:
        logger.debug("platform_history_total_cache_increment_failed username=%s", username, exc_info=True)
        return
    _seed_public_history_total(username)

def get_public_history_page(username: str, limit: int | None = None) -> dict[str, Any]:
    history_rows, effective_limit = _load_public_history(username, limit=limit)
    resolved_limit = effective_limit or len(history_rows)
    total = len(history_rows) if effective_limit is None else _get_public_history_total(username)
    return {
        "history": history_rows,
        "total": total,
        "hasMore": total > len(history_rows),
        "limit": resolved_limit,
    }

def _count_public_history_stats(username: str) -> tuple[int, int]:
    runtime_events = _load_runtime_attempt_events(username)
    seen_bridge_ids = _history_bridge_ids(runtime_events)
    runtime_total = len(runtime_events)
    runtime_correct = sum(1 for event in runtime_events if event.get("correct") is True)
    db_total, db_correct = _summarize_db_history(username=username, seen_bridge_ids=seen_bridge_ids)
    return runtime_total + db_total, runtime_correct + db_correct

def get_public_profile(username: str, history_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    profile = _normalize_skill_level_payload(learning_service.get_profile(username))
    if history_rows is not None:
        attempts = len(history_rows)
        correct = sum(1 for item in history_rows if item.get("correct") is True)
    else:
        attempts, correct = _count_public_history_stats(username)
    accuracy = round((correct / attempts) * 100, 1) if attempts else 0.0
    profile["totalAttempts"] = attempts
    profile["correctAnswers"] = correct
    profile["accuracy"] = accuracy
    return profile

def get_public_report(username: str, user_id: int, db: Session | None = None) -> dict[str, Any]:
    with _db_session(db) as session:
        if session is None:
            raise LookupError("report_not_found")
        payload = get_latest_report_detail(session, user_id)
        if payload is None:
            raise LookupError("report_not_found")
        return payload


def _elapsed_ms(started_at: float) -> int:
    return int(max((time.perf_counter() - started_at) * 1000.0, 0.0))


def _problem_request_ops_payload(language: str, difficulty: str) -> dict[str, str]:
    return {
        "language": language,
        "difficulty": difficulty,
    }


def _problem_stream_callback(
    mode: str,
    on_partial_ready: Callable[[dict[str, Any]], None] | None,
) -> Callable[[str], None] | None:
    if on_partial_ready is None:
        return None
    return lambda delta: on_partial_ready({"delta": delta, "mode": mode})


def _commit_problem_persistence(
    session: Session,
    *,
    mode: str,
    username: str,
    user_id: int,
    problem_payload: dict[str, Any],
    runtime_payload: dict[str, Any],
) -> None:
    try:
        _persist_problem(
            mode=mode,
            username=username,
            user_id=user_id,
            problem_payload=problem_payload,
            runtime_payload=runtime_payload,
            db=session,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise


def _commit_submission_persistence(
    session: Session,
    *,
    mode: str,
    username: str,
    user_id: int,
    submission_payload: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    try:
        _persist_submission(
            mode=mode,
            username=username,
            user_id=user_id,
            submission_payload=submission_payload,
            result_payload=result_payload,
            db=session,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise


def _submission_ops_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "correct": result.get("correct"),
        "score": result.get("score"),
    }


def request_mode_problem(
    *,
    mode: str,
    username: str,
    user_id: int,
    language: str,
    difficulty: str,
    db: Session | None = None,
    defer_persistence: bool = False,
    on_payload_ready: Callable[[dict[str, Any]], None] | None = None,
    on_partial_ready: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    normalized_mode = _normalize_mode(mode)
    normalized_language = normalize_language_id(language)
    if normalized_language is None:
        raise ValueError("지원하지 않는 언어입니다.")
    normalized_difficulty = str(difficulty or "beginner").strip().lower()
    started_at = time.perf_counter()
    request_ops_payload = _problem_request_ops_payload(
        normalized_language,
        normalized_difficulty,
    )
    try:
        runtime_payload = _request_runtime_problem(
            normalized_mode,
            username=username,
            language=normalized_language,
            difficulty=normalized_difficulty,
            on_text_delta=_problem_stream_callback(normalized_mode, on_partial_ready),
        )
        canonical_payload = _canonical_problem_payload(
            normalized_mode,
            runtime_payload,
            language=normalized_language,
            difficulty=normalized_difficulty,
        )
        response_payload = _response_problem_payload(normalized_mode, canonical_payload)
        if defer_persistence:
            future = _defer_problem_follow_up(
                mode=normalized_mode,
                username=username,
                user_id=user_id,
                problem_payload=canonical_payload,
                runtime_payload=runtime_payload,
                event_type="problem_requested",
                latency_ms=_elapsed_ms(started_at),
                language=normalized_language,
                difficulty=normalized_difficulty,
                allow_rq=False,
            )
            if on_payload_ready is not None:
                on_payload_ready(response_payload)
            if future is not None:
                future.result()
            return response_payload
        with _db_session(db) as session:
            if session is not None:
                _commit_problem_persistence(
                    session,
                    mode=normalized_mode,
                    username=username,
                    user_id=user_id,
                    problem_payload=canonical_payload,
                    runtime_payload=runtime_payload,
                )
        _record_ops_event_best_effort(
            db=db,
            user_id=user_id,
            event_type="problem_requested",
            mode=normalized_mode,
            status="success",
            latency_ms=_elapsed_ms(started_at),
            payload=request_ops_payload,
        )
        return response_payload
    except Exception:
        elapsed_ms = _elapsed_ms(started_at)
        if defer_persistence:
            _defer_failure_ops_event(
                user_id=user_id,
                mode=normalized_mode,
                latency_ms=elapsed_ms,
                language=normalized_language,
                difficulty=normalized_difficulty,
            )
        else:
            _record_ops_event_best_effort(
                db=db,
                user_id=user_id,
                event_type="problem_requested",
                mode=normalized_mode,
                status="failure",
                latency_ms=elapsed_ms,
                payload=request_ops_payload,
            )
        raise

def submit_mode_answer(
    *,
    mode: str,
    username: str,
    user_id: int,
    body: dict[str, Any],
    db: Session | None = None,
) -> dict[str, Any]:
    normalized_mode = _normalize_mode(mode)
    started_at = time.perf_counter()
    result = _normalize_skill_level_payload(
        _submit_runtime_answer(normalized_mode, username=username, body=dict(body))
    )
    with _db_session(db) as session:
        if session is not None:
            _commit_submission_persistence(
                session,
                mode=normalized_mode,
                username=username,
                user_id=user_id,
                submission_payload=dict(body),
                result_payload=result,
            )
    elapsed_ms = _elapsed_ms(started_at)
    _increment_public_history_total(username)
    _record_ops_event_best_effort(
        db=db,
        user_id=user_id,
        event_type="submission_processed",
        mode=normalized_mode,
        status="success" if _submission_status_from_result(result) == SubmissionStatus.passed else "review_required",
        latency_ms=elapsed_ms,
        payload=_submission_ops_payload(result),
    )
    return result
