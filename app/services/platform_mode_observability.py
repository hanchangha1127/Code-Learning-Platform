from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from app.core.request_context import get_request_id
from backend.admin_metrics import get_admin_metrics

logger = logging.getLogger(__name__)
_metrics = get_admin_metrics()


def _normalize_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    return normalized or "unknown"


def _normalize_operation(operation: str) -> str:
    normalized = str(operation or "").strip().lower()
    return normalized or "submit"


@contextmanager
def observe_platform_mode_operation(
    *,
    mode: str,
    operation: str,
    user_id: int | None = None,
    request_id: str | None = None,
) -> Iterator[None]:
    normalized_mode = _normalize_mode(mode)
    normalized_operation = _normalize_operation(operation)
    token = _metrics.start_platform_mode_call(normalized_mode, normalized_operation)
    started_at = time.perf_counter()
    resolved_request_id = str(request_id or get_request_id() or "-")
    logger.info(
        "platform_mode_operation_started mode=%s operation=%s user_id=%s request_id=%s",
        normalized_mode,
        normalized_operation,
        user_id,
        resolved_request_id,
    )

    success = False
    try:
        yield
        success = True
    except Exception as exc:
        if isinstance(exc, HTTPException):
            level = logging.WARNING if int(exc.status_code) < 500 else logging.ERROR
            logger.log(
                level,
                "platform_mode_operation_failed mode=%s operation=%s user_id=%s request_id=%s status_code=%s detail=%s",
                normalized_mode,
                normalized_operation,
                user_id,
                resolved_request_id,
                exc.status_code,
                exc.detail,
            )
        elif isinstance(exc, ValueError):
            logger.warning(
                "platform_mode_operation_failed mode=%s operation=%s user_id=%s request_id=%s error=%s",
                normalized_mode,
                normalized_operation,
                user_id,
                resolved_request_id,
                exc,
            )
        else:
            logger.exception(
                "platform_mode_operation_failed mode=%s operation=%s user_id=%s request_id=%s error=%s",
                normalized_mode,
                normalized_operation,
                user_id,
                resolved_request_id,
                exc,
            )
        raise
    finally:
        _metrics.end_platform_mode_call(token, success=success)
        latency_ms = max((time.perf_counter() - started_at) * 1000.0, 0.0)
        logger.info(
            "platform_mode_operation_finished mode=%s operation=%s user_id=%s request_id=%s success=%s latency_ms=%.2f",
            normalized_mode,
            normalized_operation,
            user_id,
            resolved_request_id,
            success,
            latency_ms,
        )


def record_platform_mode_submit_dispatch(
    *,
    mode: str,
    user_id: int,
    queued: bool,
    job_id: str | None = None,
    queue_name: str | None = None,
) -> None:
    normalized_mode = _normalize_mode(mode)
    _metrics.record_platform_mode_submit_dispatch(normalized_mode, queued=queued)
    logger.info(
        "platform_mode_submit_dispatch mode=%s user_id=%s request_id=%s queued=%s job_id=%s queue_name=%s",
        normalized_mode,
        user_id,
        str(get_request_id() or "-"),
        queued,
        job_id,
        queue_name,
    )


def record_platform_mode_enqueue_failure(*, mode: str, user_id: int, error: Exception) -> None:
    normalized_mode = _normalize_mode(mode)
    _metrics.record_platform_mode_enqueue_failure(normalized_mode)
    logger.exception(
        "platform_mode_submit_enqueue_failed mode=%s user_id=%s request_id=%s error=%s",
        normalized_mode,
        user_id,
        str(get_request_id() or "-"),
        error,
    )
