from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
import inspect
import json
import logging
import os
import threading
import time
from typing import Callable

from fastapi import Request, status
from fastapi.responses import StreamingResponse

from server.features.learning.history import ProblemFollowUpUnavailableError

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
STREAM_WORKER_MAX = _get_int_env("CODE_PLATFORM_PROBLEM_STREAM_WORKERS", 16)
STREAM_PENDING_MAX = _get_int_env(
    "CODE_PLATFORM_PROBLEM_STREAM_PENDING_MAX",
    max(STREAM_WORKER_MAX * 4, 64),
    minimum=STREAM_WORKER_MAX,
)
_STREAM_EXECUTOR = ThreadPoolExecutor(max_workers=STREAM_WORKER_MAX, thread_name_prefix="problem-stream")
_STREAM_SLOTS = threading.BoundedSemaphore(STREAM_PENDING_MAX)
GENERIC_INTERNAL_ERROR_DETAIL = "요청 처리 중 오류가 발생했습니다."
STREAM_QUEUE_FULL_MESSAGE = "요청이 많아 대기열이 가득 찼습니다."
STREAM_RETRY_MESSAGE = "요청이 많아 잠시 후 다시 시도해 주세요."
STREAM_QUEUED_MESSAGE = "문제 생성을 시작했습니다."
STREAM_GENERATING_MESSAGE = "문제를 생성 중입니다."
STREAM_PERSISTING_MESSAGE = "문제를 저장 중입니다."
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


class _ProblemStreamCancelled(Exception):
    """Internal cooperative-cancellation signal for streaming workers."""


def _wants_problem_stream(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/event-stream" in accept


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _invoke_stream_problem_work(
    work: Callable[..., dict],
    publish_payload: Callable[[dict], None],
    publish_partial: Callable[[dict], None],
) -> dict:
    try:
        parameter_count = len(inspect.signature(work).parameters)
    except (TypeError, ValueError):
        parameter_count = 1
    if parameter_count <= 0:
        return work()
    if parameter_count >= 2:
        return work(publish_payload, publish_partial)
    return work(publish_payload)


def _execute_stream_problem(operation: str, callback: Callable[[], dict]) -> dict:
    try:
        return callback()
    except _ProblemStreamCancelled:
        raise
    except ProblemFollowUpUnavailableError as exc:
        logger.warning("%s capacity exceeded: %s", operation, exc)
        raise _ProblemStreamError(
            STREAM_RETRY_MESSAGE,
            code="stream_capacity_exceeded",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=True,
        ) from exc
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
        yield _sse_event("done", {"ok": False, "code": stream_error.code, "elapsedMs": 0, "persisted": False})

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
    work: Callable[..., dict],
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
    partial_holder: dict[str, dict] = {}
    partial_lock = threading.Lock()
    started_at = time.monotonic()
    future: Future[None] | None = None

    def _merge_partial_payload(partial: dict | str | None) -> dict:
        normalized = partial if isinstance(partial, dict) else {"delta": str(partial or "")}
        merged = dict(partial_holder.get("payload") or {})
        for key, value in normalized.items():
            if key in {"delta", "text", "raw"} and value is not None:
                merged[key] = f"{merged.get(key, '')}{value}"
                continue
            merged[key] = value
        return merged

    def _publish_payload(payload: dict) -> None:
        if cancelled.is_set():
            raise _ProblemStreamCancelled()
        result_holder["payload"] = payload
        payload_ready.set()

    def _publish_partial(partial: dict) -> None:
        if cancelled.is_set():
            raise _ProblemStreamCancelled()
        with partial_lock:
            partial_holder["payload"] = _merge_partial_payload(partial)

    def _worker() -> None:
        try:
            if cancelled.is_set():
                logger.info("problem_stream_worker_skipped_after_disconnect")
                return
            payload = _invoke_stream_problem_work(work, _publish_payload, _publish_partial)
            if cancelled.is_set():
                logger.info("problem_stream_result_discarded_after_disconnect")
                return
            result_holder["payload"] = payload
            payload_ready.set()
        except _ProblemStreamCancelled:
            logger.info("problem_stream_worker_cancelled")
            return
        except _ProblemStreamError as exc:
            if cancelled.is_set():
                logger.info("problem_stream_error_discarded_after_disconnect code=%s", exc.code)
                return
            error_holder["error"] = exc
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("problem_stream_worker_failed: %s", exc)
            if cancelled.is_set():
                logger.info("problem_stream_unhandled_error_discarded_after_disconnect")
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
        def _drain_partial_events(*, elapsed_ms: int):
            while True:
                with partial_lock:
                    partial = partial_holder.pop("payload", None)
                if partial is None:
                    break
                yield _sse_event(
                    "partial",
                    {
                        **partial,
                        "elapsedMs": elapsed_ms,
                    },
                )

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
            for partial_event in _drain_partial_events(elapsed_ms=elapsed_ms):
                yield partial_event
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
            for partial_event in _drain_partial_events(elapsed_ms=elapsed_ms):
                yield partial_event
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
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            for partial_event in _drain_partial_events(elapsed_ms=elapsed_ms):
                yield partial_event
            yield _sse_event(
                "status",
                {
                    "phase": "persisting",
                    "message": STREAM_PERSISTING_MESSAGE,
                    "elapsedMs": elapsed_ms,
                },
            )
            await asyncio.sleep(STREAM_HEARTBEAT_SECONDS)

        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        for partial_event in _drain_partial_events(elapsed_ms=elapsed_ms):
            yield partial_event
        stream_error = error_holder.get("error")
        if stream_error:
            yield _sse_event("error", stream_error.to_payload(elapsed_ms=elapsed_ms))
            yield _sse_event("done", {"ok": False, "code": stream_error.code, "elapsedMs": elapsed_ms, "persisted": False})
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
        yield _sse_event("done", {"ok": True, "elapsedMs": elapsed_ms, "persisted": True})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
