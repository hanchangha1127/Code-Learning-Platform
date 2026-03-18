from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
import json
import logging
import os
import threading
import time
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from server_runtime.context import learning_service, user_service
from server_runtime.deps import get_current_username
from server_runtime.schemas import (
    AuditorSubmitRequest,
    CodeBlameSubmitRequest,
    CodeArrangeSubmitRequest,
    CodeBlockSubmitRequest,
    CodeCalcSubmitRequest,
    CodeErrorSubmitRequest,
    ContextInferenceSubmitRequest,
    DiagnosticStartRequest,
    ExplanationSubmission,
    ProblemRequest,
    RefactoringChoiceSubmitRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if not raw:
        return max(default, minimum)
    try:
        return max(int(raw), minimum)
    except (TypeError, ValueError):
        return max(default, minimum)


STREAM_HEARTBEAT_SECONDS = 0.25
STREAM_WORKER_MAX = _get_int_env("CODE_PLATFORM_PROBLEM_STREAM_WORKERS", 8)
STREAM_PENDING_MAX = _get_int_env(
    "CODE_PLATFORM_PROBLEM_STREAM_PENDING_MAX",
    STREAM_WORKER_MAX * 2,
    minimum=STREAM_WORKER_MAX,
)
_STREAM_EXECUTOR = ThreadPoolExecutor(max_workers=STREAM_WORKER_MAX, thread_name_prefix="problem-stream")
_STREAM_SLOTS = threading.BoundedSemaphore(STREAM_PENDING_MAX)
GENERIC_INTERNAL_ERROR_DETAIL = "요청 처리 중 오류가 발생했습니다."
STREAM_QUEUE_FULL_MESSAGE = "요청이 많아 대기열이 가득 찼습니다."
STREAM_RETRY_MESSAGE = "요청이 많아 잠시 후 다시 시도해 주세요."
STREAM_QUEUED_MESSAGE = "문제 생성을 시작했습니다."
STREAM_GENERATING_MESSAGE = "문제를 생성 중입니다."
STREAM_RENDERING_MESSAGE = "문제를 표시 중..."
AUTH_REQUIRED_DETAIL = "인증이 필요합니다."
LEARNING_REPORT_FAILURE_DETAIL = "학습 리포트 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."


class _ProblemStreamError(Exception):
    """User-facing generation error wrapper for SSE responses."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.retryable = retryable

    def to_payload(self, *, elapsed_ms: int) -> dict:
        return {
            "message": self.message,
            "code": self.code,
            "httpStatus": self.http_status,
            "retryable": self.retryable,
            "elapsedMs": elapsed_ms,
        }


def _wants_problem_stream(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/event-stream" in accept


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _execute_stream_problem(operation: str, callback: Callable[[], dict]) -> dict:
    try:
        return callback()
    except ValueError as exc:
        raise _ProblemStreamError(
            str(exc),
            code="validation_error",
            http_status=status.HTTP_400_BAD_REQUEST,
            retryable=False,
        ) from exc
    except Exception as exc:
        if _looks_like_timeout(exc):
            logger.warning("%s timed out: %s", operation, exc)
            raise _ProblemStreamError(
                "문제 생성 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
                code="request_timeout",
                http_status=status.HTTP_504_GATEWAY_TIMEOUT,
                retryable=True,
            ) from exc
        logger.exception("%s failed: %s", operation, exc)
        raise _ProblemStreamError(
            "request processing failed",
            code="internal_error",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            retryable=True,
        ) from exc


def _looks_like_timeout(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return any(token in message for token in ("timed out", "timeout", "deadline exceeded"))


def _stream_capacity_exceeded_response() -> StreamingResponse:
    async def _event_stream():
        yield _sse_event(
            "status",
            {
                "phase": "queued",
                "message": STREAM_QUEUE_FULL_MESSAGE,
                "elapsedMs": 0,
            },
        )
        stream_error = _ProblemStreamError(
            STREAM_RETRY_MESSAGE,
            code="stream_capacity_exceeded",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=True,
        )
        yield _sse_event("error", stream_error.to_payload(elapsed_ms=0))
        yield _sse_event("done", {"ok": False, "code": stream_error.code, "elapsedMs": 0})

    return StreamingResponse(
        _event_stream(),
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _stream_problem_response(
    *,
    request: Request,
    work: Callable[[Callable[[dict], None]], dict],
    queued_message: str = STREAM_QUEUED_MESSAGE,
    generating_message: str = STREAM_GENERATING_MESSAGE,
    rendering_message: str = STREAM_RENDERING_MESSAGE,
) -> StreamingResponse:
    if not _STREAM_SLOTS.acquire(blocking=False):
        return _stream_capacity_exceeded_response()

    result_holder: dict[str, dict] = {}
    error_holder: dict[str, _ProblemStreamError] = {}
    finished = threading.Event()
    cancelled = threading.Event()
    payload_ready = threading.Event()
    started_at = time.monotonic()
    future: Future[None] | None = None

    def _publish_payload(payload: dict) -> None:
        if cancelled.is_set():
            return
        result_holder["payload"] = payload
        payload_ready.set()

    def _worker() -> None:
        try:
            if cancelled.is_set():
                logger.info("problem_stream_worker_skipped_after_disconnect")
                return
            payload = work(_publish_payload)
            if cancelled.is_set():
                logger.info("problem_stream_result_discarded_after_disconnect")
                return
            result_holder["payload"] = payload
            payload_ready.set()
        except _ProblemStreamError as exc:
            if cancelled.is_set():
                logger.info("problem_stream_error_discarded_after_disconnect code=%s", exc.code)
                return
            if payload_ready.is_set():
                logger.warning("problem_stream_error_ignored_after_payload code=%s", exc.code)
                return
            error_holder["error"] = exc
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("problem_stream_worker_failed: %s", exc)
            if cancelled.is_set():
                logger.info("problem_stream_unhandled_error_discarded_after_disconnect")
                return
            if payload_ready.is_set():
                logger.warning("problem_stream_unhandled_error_ignored_after_payload")
                return
            error_holder["error"] = _ProblemStreamError(
                GENERIC_INTERNAL_ERROR_DETAIL,
                code="internal_error",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                retryable=True,
            )
        finally:
            finished.set()
            _STREAM_SLOTS.release()

    try:
        future = _STREAM_EXECUTOR.submit(_worker)
    except RuntimeError:
        _STREAM_SLOTS.release()
        return _stream_capacity_exceeded_response()

    async def _event_stream():
        yield _sse_event(
            "status",
            {
                "phase": "queued",
                "message": queued_message,
                "elapsedMs": 0,
            },
        )

        while not finished.is_set() and not payload_ready.is_set():
            if await request.is_disconnected():
                cancelled.set()
                if future is not None and not future.done():
                    future.cancel()
                logger.info("problem_stream_client_disconnected")
                return
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            yield _sse_event(
                "status",
                {
                    "phase": "generating",
                    "message": generating_message,
                    "elapsedMs": elapsed_ms,
                },
            )
            await asyncio.sleep(STREAM_HEARTBEAT_SECONDS)

        if await request.is_disconnected():
            cancelled.set()
            if future is not None and not future.done():
                future.cancel()
            logger.info("problem_stream_client_disconnected_after_finish")
            return

        if cancelled.is_set():
            logger.info("problem_stream_cancelled_before_emit")
            return

        payload_emitted = False
        if payload_ready.is_set():
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            payload = result_holder.get("payload", {})
            yield _sse_event(
                "status",
                {
                    "phase": "rendering",
                    "message": rendering_message,
                    "elapsedMs": elapsed_ms,
                },
            )
            yield _sse_event(
                "payload",
                {
                    "payload": payload,
                    "elapsedMs": elapsed_ms,
                },
            )
            payload_emitted = True

        while not finished.is_set():
            if await request.is_disconnected():
                cancelled.set()
                if future is not None and not future.done():
                    future.cancel()
                logger.info("problem_stream_client_disconnected_after_payload")
                return
            await asyncio.sleep(STREAM_HEARTBEAT_SECONDS)

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        stream_error = error_holder.get("error")
        if stream_error and not payload_emitted:
            yield _sse_event("error", stream_error.to_payload(elapsed_ms=elapsed_ms))
            yield _sse_event("done", {"ok": False, "code": stream_error.code, "elapsedMs": elapsed_ms})
            return

        if not payload_emitted:
            payload = result_holder.get("payload", {})
            yield _sse_event(
                "status",
                {
                    "phase": "rendering",
                    "message": rendering_message,
                    "elapsedMs": elapsed_ms,
                },
            )
            yield _sse_event(
                "payload",
                {
                    "payload": payload,
                    "elapsedMs": elapsed_ms,
                },
            )
        yield _sse_event("done", {"ok": True, "elapsedMs": elapsed_ms})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _require_username(username: str) -> None:
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_REQUIRED_DETAIL)


@router.get("/api/tracks")
def list_tracks(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return {"tracks": learning_service.list_tracks()}


@router.get("/api/languages")
def list_languages(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return {"languages": learning_service.list_languages()}


@router.get("/api/profile")
def profile(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return learning_service.get_profile(username)


@router.get("/api/me")
def me(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return user_service.get_user_info(username)


@router.post("/api/diagnostics/start")
def start_diagnostic(
    selection: DiagnosticStartRequest,
    request: Request,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                "start_diagnostic",
                lambda: learning_service.request_problem(
                    username,
                    selection.language_id,
                    selection.difficulty,
                ),
            )
        )

    try:
        return learning_service.request_problem(
            username,
            selection.language_id,
            selection.difficulty,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/problem/submit")
def submit_explanation(
    submission: ExplanationSubmission,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_explanation(
            username,
            submission.language_id,
            submission.problem_id,
            submission.explanation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_explanation failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-block/problem")
def request_code_block_problem(
    payload: ProblemRequest,
    request: Request,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                "request_code_block_problem",
                lambda: learning_service.request_code_block_problem(
                    username,
                    payload.language_id,
                    payload.difficulty_id,
                ),
            )
        )

    try:
        return learning_service.request_code_block_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_block_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-block/submit")
def submit_code_block_answer(
    submission: CodeBlockSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_block_answer(
            username,
            submission.problem_id,
            submission.selected_option,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_block_answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-arrange/problem")
def request_code_arrange_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_code_arrange_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_arrange_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-arrange/submit")
def submit_code_arrange_answer(
    submission: CodeArrangeSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_arrange_answer(
            username,
            submission.problem_id,
            submission.order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_arrange_answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-calc/problem")
def request_code_calc_problem(
    payload: ProblemRequest,
    request: Request,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                "request_code_calc_problem",
                lambda: learning_service.request_code_calc_problem(
                    username,
                    payload.language_id,
                    payload.difficulty_id,
                ),
            )
        )

    try:
        return learning_service.request_code_calc_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_calc_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-calc/submit")
def submit_code_calc_answer(
    submission: CodeCalcSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_calc_answer(
            username,
            submission.problem_id,
            submission.output_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_calc_answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-error/problem")
def request_code_error_problem(
    payload: ProblemRequest,
    request: Request,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                "request_code_error_problem",
                lambda: learning_service.request_code_error_problem(
                    username,
                    payload.language_id,
                    payload.difficulty_id,
                ),
            )
        )

    try:
        return learning_service.request_code_error_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_error_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-error/submit")
def submit_code_error_answer(
    submission: CodeErrorSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_error_answer(
            username,
            submission.problem_id,
            submission.selected_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_error_answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/auditor/problem")
def request_auditor_problem(
    payload: ProblemRequest,
    request: Request,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                "request_auditor_problem",
                lambda: learning_service.request_auditor_problem(
                    username,
                    payload.language_id,
                    payload.difficulty_id,
                ),
            )
        )

    try:
        return learning_service.request_auditor_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_auditor_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/auditor/submit")
def submit_auditor_report(
    submission: AuditorSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_auditor_report(
            username,
            submission.problem_id,
            submission.report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_auditor_report failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/context-inference/problem")
def request_context_inference_problem(
    payload: ProblemRequest,
    request: Request,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                "request_context_inference_problem",
                lambda: learning_service.request_context_inference_problem(
                    username,
                    payload.language_id,
                    payload.difficulty_id,
                ),
            )
        )

    try:
        return learning_service.request_context_inference_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_context_inference_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/context-inference/submit")
def submit_context_inference_report(
    submission: ContextInferenceSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_context_inference_report(
            username,
            submission.problem_id,
            submission.report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_context_inference_report failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/refactoring-choice/problem")
def request_refactoring_choice_problem(
    payload: ProblemRequest,
    request: Request,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                "request_refactoring_choice_problem",
                lambda: learning_service.request_refactoring_choice_problem(
                    username,
                    payload.language_id,
                    payload.difficulty_id,
                ),
            )
        )

    try:
        return learning_service.request_refactoring_choice_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_refactoring_choice_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/refactoring-choice/submit")
def submit_refactoring_choice_report(
    submission: RefactoringChoiceSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_refactoring_choice_report(
            username,
            submission.problem_id,
            submission.selected_option,
            submission.report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_refactoring_choice_report failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-blame/problem")
def request_code_blame_problem(
    payload: ProblemRequest,
    request: Request,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                "request_code_blame_problem",
                lambda: learning_service.request_code_blame_problem(
                    username,
                    payload.language_id,
                    payload.difficulty_id,
                ),
            )
        )

    try:
        return learning_service.request_code_blame_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_blame_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.post("/api/code-blame/submit")
def submit_code_blame_report(
    submission: CodeBlameSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_blame_report(
            username,
            submission.problem_id,
            submission.selected_commits,
            submission.report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_blame_report failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=GENERIC_INTERNAL_ERROR_DETAIL) from exc


@router.get("/api/learning/history")
def history(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    events = learning_service.user_history(username)
    return {"history": events}


@router.get("/api/learning/memory")
def memory(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    memo = learning_service.user_memory(username)
    return {"memory": memo}


@router.get("/api/report")
def report(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    try:
        return learning_service.learning_report(username)
    except RuntimeError as exc:
        if "learning_report_generation_failed" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=LEARNING_REPORT_FAILURE_DETAIL,
            ) from exc
        raise

