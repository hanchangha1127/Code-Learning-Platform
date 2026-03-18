from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    AIAnalysis,
    AnalysisType,
    Problem,
    ProblemContentStatus,
    ProblemDifficulty,
    ProblemKind,
    Report,
    ReportType,
    Submission,
    SubmissionStatus,
    User,
    UserProblemStat,
)
from app.services.learning_continuity_service import sync_review_queue_for_submission
from app.services.platform_ops_service import record_ops_event
from app.db.session import SessionLocal
from app.services.problem_stat_service import classify_wrong_answer_type, update_user_problem_stat
from backend.learning_reporting import trend_summary
from server_runtime.context import learning_service, storage_manager, user_service

logger = logging.getLogger(__name__)
_PROBLEM_FOLLOW_UP_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="problem-follow-up")
_PROBLEM_FOLLOW_UP_SLOTS = threading.BoundedSemaphore(128)

_PROBLEM_KIND_BY_MODE: dict[str, ProblemKind] = {
    "analysis": ProblemKind.analysis,
    "code-block": ProblemKind.code_block,
    "code-arrange": ProblemKind.code_arrange,
    "code-calc": ProblemKind.code_calc,
    "code-error": ProblemKind.code_error,
    "auditor": ProblemKind.auditor,
    "context-inference": ProblemKind.context_inference,
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
    "code-calc": AnalysisType.explain,
    "code-error": AnalysisType.error,
    "auditor": AnalysisType.review,
    "context-inference": AnalysisType.review,
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
    "code-calc": "code_calc_event",
    "code-error": "code_error_event",
    "auditor": "auditor_event",
    "context-inference": "context_inference_event",
    "refactoring-choice": "refactoring_choice_event",
    "code-blame": "code_blame_event",
    "single-file-analysis": "single_file_analysis_event",
    "multi-file-analysis": "multi_file_analysis_event",
    "fullstack-analysis": "fullstack_analysis_event",
}


def list_public_languages() -> list[dict[str, str]]:
    return learning_service.list_languages()


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


def get_public_history(username: str) -> list[dict[str, Any]]:
    history = learning_service.user_history(username)
    seen_bridge_ids = {
        str(item.get("bridgeId") or item.get("bridge_id") or "").strip()
        for item in history
        if str(item.get("bridgeId") or item.get("bridge_id") or "").strip()
    }
    db_history = _load_db_history(username=username, seen_bridge_ids=seen_bridge_ids)
    merged = history + db_history
    merged.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return merged


def get_public_memory(username: str) -> list[dict[str, Any]]:
    return learning_service.user_memory(username)


def get_public_profile(username: str, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    profile = learning_service.get_profile(username)
    history = history if history is not None else get_public_history(username)
    attempts = len(history)
    correct = sum(1 for item in history if item.get("correct") is True)
    accuracy = round((correct / attempts) * 100, 1) if attempts else 0.0
    profile["totalAttempts"] = attempts
    profile["correctAnswers"] = correct
    profile["accuracy"] = accuracy
    return profile


def get_public_report(username: str, user_id: int, db: Session | None = None) -> dict[str, Any]:
    payload = learning_service.learning_report(username)
    metric_snapshot = _build_metric_snapshot(get_public_history(username))
    payload["metricSnapshot"] = metric_snapshot
    created_at = utcnow().isoformat()
    payload["createdAt"] = created_at

    bridge_id = f"report-{uuid4().hex}"
    payload["bridgeId"] = bridge_id
    _append_jsonl_record(
        username,
        {
            "type": "learning_report",
            "source": "platform",
            "bridgeId": bridge_id,
            "created_at": created_at,
            "payload": payload,
        },
    )

    with _db_session(db) as session:
        if session is None:
            payload["reportId"] = None
            return payload

        report = Report(
            user_id=user_id,
            report_type=ReportType.milestone,
            period_start=None,
            period_end=None,
            milestone_problem_count=int(metric_snapshot.get("attempts") or 0),
            title=str(payload.get("goal") or "\uD559\uC2B5 \uB9AC\uD3EC\uD2B8")[:200],
            summary=str(payload.get("solutionSummary") or ""),
            strengths=[],
            weaknesses=[],
            recommendations=payload.get("priorityActions") if isinstance(payload.get("priorityActions"), list) else [],
            stats={
                "source": "platform",
                "bridgeId": bridge_id,
                "solutionPlan": payload,
                "metricSnapshot": metric_snapshot,
            },
            created_at=utcnow(),
        )
        session.add(report)
        record_ops_event(
            session,
            user_id=user_id,
            event_type="learning_report_generated",
            status="success",
            payload={
                "attempts": metric_snapshot.get("attempts"),
                "accuracy": metric_snapshot.get("accuracy"),
            },
        )
        session.commit()
        session.refresh(report)
        payload["reportId"] = report.id
        payload["createdAt"] = report.created_at.isoformat() if report.created_at else created_at
        return payload


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
) -> dict[str, Any]:
    normalized_mode = _normalize_mode(mode)
    normalized_language = str(language or "python").strip().lower()
    normalized_difficulty = str(difficulty or "beginner").strip().lower()
    started_at = time.perf_counter()
    try:
        runtime_payload = _request_runtime_problem(
            normalized_mode,
            username=username,
            language=normalized_language,
            difficulty=normalized_difficulty,
        )
        canonical_payload = _canonical_problem_payload(
            normalized_mode,
            runtime_payload,
            language=normalized_language,
            difficulty=normalized_difficulty,
        )
        response_payload = _response_problem_payload(normalized_mode, canonical_payload)
        if defer_persistence:
            if on_payload_ready is not None:
                on_payload_ready(response_payload)
            elapsed_ms = int(max((time.perf_counter() - started_at) * 1000.0, 0.0))
            _defer_problem_follow_up(
                mode=normalized_mode,
                username=username,
                user_id=user_id,
                problem_payload=canonical_payload,
                runtime_payload=runtime_payload,
                event_type="problem_requested",
                latency_ms=elapsed_ms,
                language=normalized_language,
                difficulty=normalized_difficulty,
            )
            return response_payload
        with _db_session(db) as session:
            if session is not None:
                try:
                    _persist_problem(
                        mode=normalized_mode,
                        username=username,
                        user_id=user_id,
                        problem_payload=canonical_payload,
                        runtime_payload=runtime_payload,
                        db=session,
                    )
                    session.commit()
                except Exception:
                    session.rollback()
                    raise
        elapsed_ms = int(max((time.perf_counter() - started_at) * 1000.0, 0.0))
        _record_ops_event_best_effort(
            db=db,
            user_id=user_id,
            event_type="problem_requested",
            mode=normalized_mode,
            status="success",
            latency_ms=elapsed_ms,
            payload={"language": normalized_language, "difficulty": normalized_difficulty},
        )
        return response_payload
    except Exception:
        elapsed_ms = int(max((time.perf_counter() - started_at) * 1000.0, 0.0))
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
                payload={"language": normalized_language, "difficulty": normalized_difficulty},
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
    submission_payload = dict(body)
    started_at = time.perf_counter()
    try:
        result = _submit_runtime_answer(normalized_mode, username=username, body=submission_payload)
        with _db_session(db) as session:
            if session is not None:
                try:
                    _persist_submission(
                        mode=normalized_mode,
                        username=username,
                        user_id=user_id,
                        submission_payload=submission_payload,
                        result_payload=result,
                        db=session,
                    )
                    session.commit()
                except Exception:
                    session.rollback()
                    raise
        elapsed_ms = int(max((time.perf_counter() - started_at) * 1000.0, 0.0))
        _record_ops_event_best_effort(
            db=db,
            user_id=user_id,
            event_type="submission_processed",
            mode=normalized_mode,
            status="success" if _submission_status_from_result(result) == SubmissionStatus.passed else "review_required",
            latency_ms=elapsed_ms,
            payload={"correct": result.get("correct"), "score": result.get("score")},
        )
        return result
    except Exception:
        elapsed_ms = int(max((time.perf_counter() - started_at) * 1000.0, 0.0))
        _record_ops_event_best_effort(
            db=db,
            user_id=user_id,
            event_type="submission_processed",
            mode=normalized_mode,
            status="failure",
            latency_ms=elapsed_ms,
        )
        raise


def _normalize_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in _PROBLEM_KIND_BY_MODE:
        raise ValueError(f"unsupported mode: {mode}")
    return normalized


def _request_runtime_problem(mode: str, *, username: str, language: str, difficulty: str) -> dict[str, Any]:
    if mode == "analysis":
        return learning_service.request_problem(username, language, difficulty)
    if mode == "code-block":
        return learning_service.request_code_block_problem(username, language, difficulty)
    if mode == "code-arrange":
        return learning_service.request_code_arrange_problem(username, language, difficulty)
    if mode == "code-calc":
        return learning_service.request_code_calc_problem(username, language, difficulty)
    if mode == "code-error":
        return learning_service.request_code_error_problem(username, language, difficulty)
    if mode == "auditor":
        return learning_service.request_auditor_problem(username, language, difficulty)
    if mode == "context-inference":
        return learning_service.request_context_inference_problem(username, language, difficulty)
    if mode == "refactoring-choice":
        return learning_service.request_refactoring_choice_problem(username, language, difficulty)
    if mode == "code-blame":
        return learning_service.request_code_blame_problem(username, language, difficulty)
    if mode == "single-file-analysis":
        return learning_service.request_single_file_analysis_problem(username, language, difficulty)
    if mode == "multi-file-analysis":
        return learning_service.request_multi_file_analysis_problem(username, language, difficulty)
    if mode == "fullstack-analysis":
        return learning_service.request_fullstack_analysis_problem(username, language, difficulty)
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
    if mode == "code-calc":
        return learning_service.submit_code_calc_answer(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            str(body.get("output") or body.get("outputText") or body.get("output_text") or ""),
        )
    if mode == "code-error":
        selected_index = body.get("selectedIndex")
        if selected_index is None:
            selected_index = body.get("selected_index")
        return learning_service.submit_code_error_answer(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            int(selected_index),
        )
    if mode == "auditor":
        return learning_service.submit_auditor_report(
            username,
            str(body.get("problemId") or body.get("problem_id") or ""),
            str(body.get("report") or ""),
        )
    if mode == "context-inference":
        return learning_service.submit_context_inference_report(
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


def _record_ops_event_best_effort(
    *,
    db: Session | None = None,
    user_id: int | None,
    event_type: str,
    mode: str | None = None,
    status: str | None = None,
    latency_ms: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        with _db_session(db) as session:
            if session is None:
                return
            try:
                record_ops_event(
                    session,
                    user_id=user_id,
                    event_type=event_type,
                    mode=mode,
                    status=status,
                    latency_ms=latency_ms,
                    payload=payload,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise
    except Exception:
        logger.exception(
            "platform_bridge_failed_to_record_ops_event event_type=%s mode=%s user_id=%s",
            event_type,
            mode,
            user_id,
        )


def _defer_problem_follow_up(
    *,
    mode: str,
    username: str,
    user_id: int,
    problem_payload: dict[str, Any],
    runtime_payload: dict[str, Any],
    event_type: str,
    latency_ms: int,
    language: str,
    difficulty: str,
) -> None:
    def _run_follow_up() -> None:
        try:
            _persist_problem(
                mode=mode,
                username=username,
                user_id=user_id,
                problem_payload=problem_payload,
                runtime_payload=runtime_payload,
            )
            _record_ops_event_best_effort(
                user_id=user_id,
                event_type=event_type,
                mode=mode,
                status="success",
                latency_ms=latency_ms,
                payload={"language": language, "difficulty": difficulty},
            )
        except Exception:
            logger.exception(
                "platform_bridge_problem_follow_up_failed mode=%s user_id=%s problem_id=%s",
                mode,
                user_id,
                problem_payload.get("problemId"),
            )

    if not _PROBLEM_FOLLOW_UP_SLOTS.acquire(blocking=False):
        logger.warning(
            "platform_bridge_problem_follow_up_queue_full mode=%s user_id=%s problem_id=%s",
            mode,
            user_id,
            problem_payload.get("problemId"),
        )
        _run_follow_up()
        return

    def _run_and_release() -> None:
        try:
            _run_follow_up()
        finally:
            _PROBLEM_FOLLOW_UP_SLOTS.release()

    try:
        _PROBLEM_FOLLOW_UP_EXECUTOR.submit(_run_and_release)
    except RuntimeError:
        _PROBLEM_FOLLOW_UP_SLOTS.release()
        logger.warning(
            "platform_bridge_problem_follow_up_executor_unavailable mode=%s user_id=%s problem_id=%s",
            mode,
            user_id,
            problem_payload.get("problemId"),
        )
        _run_follow_up()


def _defer_failure_ops_event(
    *,
    user_id: int,
    mode: str,
    latency_ms: int,
    language: str,
    difficulty: str,
) -> None:
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
        _record_ops_event_best_effort(
            user_id=user_id,
            event_type="problem_requested",
            mode=mode,
            status="failure",
            latency_ms=latency_ms,
            payload={"language": language, "difficulty": difficulty},
        )


def _canonical_problem_payload(
    mode: str,
    payload: dict[str, Any],
    *,
    language: str,
    difficulty: str,
) -> dict[str, Any]:
    normalized_payload = dict(payload)
    if mode != "analysis":
        return normalized_payload

    legacy_problem = payload.get("problem")
    canonical_problem = dict(legacy_problem) if isinstance(legacy_problem, dict) else {}
    canonical_payload = {**canonical_problem, **{key: value for key, value in normalized_payload.items() if key != "problem"}}

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
    return canonical_payload


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

    with _db_session(db) as session:
        if session is None:
            return

        problem = (
            session.query(Problem)
            .filter(Problem.external_id == problem_id, Problem.created_by == user_id)
            .order_by(Problem.id.desc())
            .first()
        )
        if problem is None:
            problem = Problem(
                external_id=problem_id,
                kind=_PROBLEM_KIND_BY_MODE[mode],
                title=_problem_title(combined_payload, mode),
                description=_problem_description(combined_payload),
                difficulty=_problem_difficulty(combined_payload),
                language=_problem_language(combined_payload),
                starter_code=_problem_starter_code(combined_payload),
                problem_payload=combined_payload,
                answer_payload=instance or None,
                options=_problem_options(combined_payload),
                answer_index=_problem_answer_index(instance),
                reference_solution=_problem_reference_solution(instance),
                prompt_version=_problem_prompt_version(combined_payload, mode),
                content_status=ProblemContentStatus.pending,
                is_curated_sample=False,
                is_published=False,
                created_by=user_id,
            )
            session.add(problem)
        else:
            problem.kind = _PROBLEM_KIND_BY_MODE[mode]
            problem.title = _problem_title(combined_payload, mode)
            problem.description = _problem_description(combined_payload)
            problem.difficulty = _problem_difficulty(combined_payload)
            problem.language = _problem_language(combined_payload)
            problem.starter_code = _problem_starter_code(combined_payload)
            problem.problem_payload = combined_payload
            problem.answer_payload = instance or problem.answer_payload
            problem.options = _problem_options(combined_payload)
            problem.answer_index = _problem_answer_index(instance)
            problem.reference_solution = _problem_reference_solution(instance)
            problem.prompt_version = _problem_prompt_version(combined_payload, mode)

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

        problem = (
            session.query(Problem)
            .filter(Problem.external_id == problem_id, Problem.created_by == user_id)
            .order_by(Problem.id.desc())
            .first()
        )
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

        submission_status = _submission_status_from_result(result_payload)
        submission_score = _submission_score(result_payload)
        stored_submission_payload = dict(submission_payload)
        stored_submission_payload["bridgeId"] = bridge_id
        stored_submission_payload["source"] = "platform"

        submission = Submission(
            user_id=user_id,
            problem_id=problem.id,
            language=problem.language,
            code=_submission_code(mode, submission_payload),
            submission_payload=stored_submission_payload,
            status=submission_status,
            score=submission_score,
        )
        session.add(submission)
        session.flush()

        result_detail_json = json.dumps(
            {
                **result_payload,
                "bridgeId": bridge_id,
                "source": "platform",
            },
            ensure_ascii=False,
        )
        summary = _feedback_summary(result_payload) or result_payload.get("verdict") or "analysis_completed"

        session.add(
            AIAnalysis(
                user_id=user_id,
                submission_id=submission.id,
                analysis_type=_ANALYSIS_TYPE_BY_MODE[mode],
                result_summary=str(summary)[:1000],
                result_detail=result_detail_json[:10000],
                result_payload={
                    **result_payload,
                    "bridgeId": bridge_id,
                    "source": "platform",
                },
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
    problem = Problem(
        external_id=problem_id,
        kind=_PROBLEM_KIND_BY_MODE[mode],
        title=_problem_title(combined_payload, mode),
        description=_problem_description(combined_payload),
        difficulty=_problem_difficulty(combined_payload),
        language=_problem_language(combined_payload),
        starter_code=_problem_starter_code(combined_payload),
        problem_payload=combined_payload,
        answer_payload=instance,
        options=_problem_options(combined_payload),
        answer_index=_problem_answer_index(instance),
        reference_solution=_problem_reference_solution(instance),
        prompt_version=_problem_prompt_version(combined_payload, mode),
        content_status=ProblemContentStatus.pending,
        is_curated_sample=False,
        is_published=False,
        created_by=user_id,
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
        "analysis": "\uCF54\uB4DC \uBD84\uC11D \uBB38\uC81C",
        "code-block": "\uCF54\uB4DC \uBE14\uB85D \uBB38\uC81C",
        "code-arrange": "\uCF54\uB4DC \uBC30\uCE58 \uBB38\uC81C",
        "code-calc": "\uCF54\uB4DC \uACC4\uC0B0 \uBB38\uC81C",
        "code-error": "\uCF54\uB4DC \uC624\uB958 \uBB38\uC81C",
        "auditor": "\uAC10\uC0AC\uAD00 \uBB38\uC81C",
        "context-inference": "\uB9E5\uB77D \uCD94\uB860 \uBB38\uC81C",
        "refactoring-choice": "\uCD5C\uC801\uC758 \uC120\uD0DD \uBB38\uC81C",
        "code-blame": "\uBC94\uC778 \uCC3E\uAE30 \uBB38\uC81C",
    }
    return fallback.get(mode, "\uD559\uC2B5 \uBB38\uC81C")


def _problem_description(payload: dict[str, Any]) -> str:
    for candidate in (
        payload.get("prompt"),
        payload.get("scenario"),
        payload.get("description"),
        payload.get("title"),
        "\uD559\uC2B5 \uBB38\uC81C",
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return "\uD559\uC2B5 \uBB38\uC81C"


def _problem_prompt_version(payload: dict[str, Any], mode: str) -> str:
    for key in ("promptVersion", "prompt_version"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value[:80]
    return f"{mode}-runtime-v1"[:80]


def _problem_language(payload: dict[str, Any]) -> str:
    return str(payload.get("language") or payload.get("languageId") or "python").strip().lower()


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
    if mode == "code-calc":
        return str(submission_payload.get("output") or submission_payload.get("outputText") or submission_payload.get("output_text") or "")
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
    normalized_mode = _normalize_mode(mode)
    event_type = _EVENT_TYPE_BY_MODE[normalized_mode]
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
        if normalized_mode == "analysis" and str(item.get("mode") or "").strip().lower() == "code-block":
            continue
        if normalized_mode == "code-block" and str(item.get("mode") or "").strip().lower() != "code-block":
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


def _load_db_history(*, username: str, seen_bridge_ids: set[str]) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        if user is None:
            return []

        rows = (
            session.query(Submission)
            .join(Problem, Problem.id == Submission.problem_id)
            .filter(Submission.user_id == user.id)
            .order_by(Submission.id.desc())
            .all()
        )
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
            analysis = _latest_submission_analysis(submission.analyses or [])
            result_payload = analysis.result_payload if analysis and isinstance(analysis.result_payload, dict) else {}
            mode = str(problem_payload.get("mode") or "").strip() or _mode_from_problem_kind(problem.kind)
            item = {
                "source": "platform",
                "bridgeId": bridge_id or None,
                "created_at": submission.created_at.isoformat() if submission.created_at else "",
                "problem_id": problem.external_id or str(problem.id),
                "mode": mode,
                "correct": submission.status == SubmissionStatus.passed,
                "score": submission.score,
                "feedback": result_payload.get("feedback") if isinstance(result_payload.get("feedback"), dict) else {},
                "summary": _feedback_summary(result_payload) or problem.title,
                "language": problem_payload.get("language") or problem.language,
                "difficulty": problem_payload.get("difficulty") or "intermediate",
                "problem_title": problem_payload.get("title") or problem.title,
                "problem_prompt": problem_payload.get("prompt") or problem.description,
                "problem_code": _problem_starter_code(problem_payload) or problem.starter_code,
                "problem_blocks": problem_payload.get("blocks"),
                "problem_options": problem_payload.get("options"),
                "problem_commits": problem_payload.get("commits"),
                "explanation": _db_history_explanation(mode, submission, payload),
            }
            if mode == "auditor":
                item["found_types"] = result_payload.get("foundTypes") or result_payload.get("found_types") or []
                item["missed_types"] = result_payload.get("missedTypes") or result_payload.get("missed_types") or []
                item["reference_report"] = result_payload.get("referenceReport") or ""
            if mode == "context-inference":
                item["found_types"] = result_payload.get("foundTypes") or result_payload.get("found_types") or []
                item["missed_types"] = result_payload.get("missedTypes") or result_payload.get("missed_types") or []
                item["reference_report"] = result_payload.get("referenceReport") or ""
                item["inference_type"] = problem_payload.get("inferenceType") or problem_payload.get("inference_type")
            if mode == "refactoring-choice":
                item["found_types"] = result_payload.get("foundTypes") or result_payload.get("found_types") or []
                item["missed_types"] = result_payload.get("missedTypes") or result_payload.get("missed_types") or []
                item["reference_report"] = result_payload.get("referenceReport") or ""
                item["selected_option"] = payload.get("selectedOption") or payload.get("selected_option") or ""
                item["best_option"] = result_payload.get("bestOption") or result_payload.get("best_option") or ""
                item["option_reviews"] = result_payload.get("optionReviews") or result_payload.get("option_reviews") or []
                item["problem_scenario"] = problem_payload.get("scenario") or ""
            if mode == "code-blame":
                item["found_types"] = result_payload.get("foundTypes") or result_payload.get("found_types") or []
                item["missed_types"] = result_payload.get("missedTypes") or result_payload.get("missed_types") or []
                item["reference_report"] = result_payload.get("referenceReport") or ""
                item["selected_commits"] = payload.get("selectedCommits") or payload.get("selected_commits") or []
                item["culprit_commits"] = result_payload.get("culpritCommits") or result_payload.get("culprit_commits") or []
                item["commit_reviews"] = result_payload.get("commitReviews") or result_payload.get("commit_reviews") or []
                item["problem_error_log"] = problem_payload.get("errorLog") or problem_payload.get("error_log") or ""
            if mode in {"single-file-analysis", "multi-file-analysis", "fullstack-analysis"}:
                item["reference_report"] = result_payload.get("referenceReport") or ""
            items.append(item)
        return items


def _mode_from_problem_kind(kind: ProblemKind | str) -> str:
    value = kind.value if hasattr(kind, "value") else str(kind)
    return {
        "analysis": "analysis",
        "code_block": "code-block",
        "code_arrange": "code-arrange",
        "code_calc": "code-calc",
        "code_error": "code-error",
        "auditor": "auditor",
        "context_inference": "context-inference",
        "refactoring_choice": "refactoring-choice",
        "code_blame": "code-blame",
    }.get(value, "analysis")


def _db_history_explanation(mode: str, submission: Submission, payload: dict[str, Any]) -> str | None:
    if mode == "analysis":
        return submission.code or None
    if mode == "code-block":
        selected = payload.get("selectedOption") or payload.get("selected_option")
        if selected is None:
            return None
        return f"\uC120\uD0DD: {selected}"
    if mode == "code-calc":
        return f"\uC81C\uCD9C \uCD9C\uB825: {submission.code}" if submission.code else None
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
