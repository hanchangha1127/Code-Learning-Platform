from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.api.security_deps import get_current_user
from app.db.models import User
from app.schemas.platform_mode_queue import PlatformModeSubmitJobStatusResponse
from app.services.analysis_queue import get_redis_connection, is_rq_enabled

router = APIRouter()


def _normalized_status(raw_status: str) -> str:
    if isinstance(raw_status, bytes):
        token = raw_status.decode("utf-8", errors="ignore").strip().lower()
    else:
        token = str(raw_status or "").strip().lower()
    if token in {"queued", "deferred", "scheduled"}:
        return "queued"
    if token in {"started", "busy"}:
        return "started"
    if token == "finished":
        return "finished"
    if token in {"failed", "stopped", "canceled", "cancelled"}:
        return "failed"
    return "queued"


def _extract_owner_user_id(job: Job) -> int | None:
    meta = getattr(job, "meta", None)
    if isinstance(meta, dict) and meta.get("user_id") is not None:
        try:
            return int(meta.get("user_id"))
        except Exception:
            return None

    args = getattr(job, "args", ()) or ()
    if len(args) >= 2:
        try:
            return int(args[1])
        except Exception:
            return None
    return None


def _extract_error(job: Job) -> str | None:
    exc_info_raw = getattr(job, "exc_info", "") or ""
    if isinstance(exc_info_raw, bytes):
        exc_info = exc_info_raw.decode("utf-8", errors="ignore").strip()
    else:
        exc_info = str(exc_info_raw).strip()
    if not exc_info:
        return None
    last_line = exc_info.splitlines()[-1].strip()
    return (last_line or exc_info)[:300]


@router.get("/{job_id}", response_model=PlatformModeSubmitJobStatusResponse)
def get_mode_submit_job_status(
    job_id: str,
    current: User = Depends(get_current_user),
):
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    if not is_rq_enabled():
        raise HTTPException(status_code=400, detail="Mode job status is available only when queue mode is rq")

    try:
        redis_conn = get_redis_connection()
        job = Job.fetch(normalized_job_id, connection=redis_conn)
    except NoSuchJobError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Failed to load job status") from exc

    owner_user_id = _extract_owner_user_id(job)
    try:
        current_user_id = int(current.id)
    except Exception:
        current_user_id = None
    if owner_user_id is None or current_user_id != owner_user_id:
        raise HTTPException(status_code=404, detail="Job not found")

    status_value = _normalized_status(job.get_status(refresh=True))
    response = PlatformModeSubmitJobStatusResponse(
        jobId=normalized_job_id,
        status=status_value,
        queued=status_value == "queued",
        finished=status_value == "finished",
        failed=status_value == "failed",
    )

    if status_value == "finished":
        result = getattr(job, "result", None)
        if isinstance(result, dict):
            response.result = result
        elif result is not None:
            response.result = {"value": str(result)}

    if status_value == "failed":
        response.error = _extract_error(job)

    return response
