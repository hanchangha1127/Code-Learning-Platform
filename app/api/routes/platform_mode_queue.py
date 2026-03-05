from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from app.core.request_context import ensure_request_id
from app.schemas.platform_mode_queue import PlatformModeSubmitQueuedResponse
from app.services.analysis_queue import enqueue_platform_mode_submit_job, is_rq_enabled
from app.services.platform_mode_observability import (
    record_platform_mode_enqueue_failure,
    record_platform_mode_submit_dispatch,
)


def execute_platform_mode_submit(
    *,
    mode: str,
    user_id: int,
    payload: dict[str, Any],
    inline_submit: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if not is_rq_enabled():
        record_platform_mode_submit_dispatch(
            mode=mode,
            user_id=user_id,
            queued=False,
        )
        return inline_submit()

    request_id = ensure_request_id()
    queued_payload = dict(payload)
    queued_payload["request_id"] = request_id

    try:
        enqueued = enqueue_platform_mode_submit_job(
            mode=mode,
            user_id=user_id,
            payload=queued_payload,
            request_id=request_id,
        )
    except Exception as exc:
        record_platform_mode_enqueue_failure(
            mode=mode,
            user_id=user_id,
            error=exc,
        )
        raise HTTPException(status_code=503, detail="Failed to enqueue mode submission job") from exc

    record_platform_mode_submit_dispatch(
        mode=mode,
        user_id=user_id,
        queued=True,
        job_id=enqueued.job_id,
        queue_name=enqueued.queue_name,
    )

    return PlatformModeSubmitQueuedResponse(
        queued=True,
        message="Submission queued",
        jobId=enqueued.job_id,
    ).model_dump()
