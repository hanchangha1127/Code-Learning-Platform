from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redis import Redis
from rq import Queue

from app.core.config import settings


@dataclass(frozen=True)
class QueueEnqueueResult:
    job_id: str
    queue_name: str


def is_rq_enabled() -> bool:
    return (settings.ANALYSIS_QUEUE_MODE or "inline").lower() == "rq"


def get_redis_connection() -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        socket_connect_timeout=3,
        socket_timeout=5,
        decode_responses=False,
    )


def get_analysis_queue() -> Queue:
    redis_conn = get_redis_connection()
    return Queue(name=settings.ANALYSIS_QUEUE_NAME, connection=redis_conn)


def enqueue_analysis_job(submission_id: int, user_id: int) -> QueueEnqueueResult:
    queue = get_analysis_queue()
    job = queue.enqueue(
        "app.services.analysis_service.run_analysis_background",
        submission_id,
        user_id,
        job_timeout=settings.ANALYSIS_QUEUE_JOB_TIMEOUT_SECONDS,
        result_ttl=settings.ANALYSIS_QUEUE_RESULT_TTL_SECONDS,
        failure_ttl=settings.ANALYSIS_QUEUE_FAILURE_TTL_SECONDS,
    )
    return QueueEnqueueResult(job_id=job.id, queue_name=queue.name)


def enqueue_platform_mode_submit_job(
    *,
    mode: str,
    user_id: int,
    payload: dict[str, Any],
    request_id: str | None = None,
) -> QueueEnqueueResult:
    queue = get_analysis_queue()
    job = queue.enqueue(
        "app.services.platform_mode_executor.run_platform_mode_submit_background",
        mode,
        user_id,
        payload,
        job_timeout=settings.ANALYSIS_QUEUE_JOB_TIMEOUT_SECONDS,
        result_ttl=settings.ANALYSIS_QUEUE_RESULT_TTL_SECONDS,
        failure_ttl=settings.ANALYSIS_QUEUE_FAILURE_TTL_SECONDS,
    )
    job.meta["user_id"] = int(user_id)
    job.meta["mode"] = str(mode or "").strip().lower()
    if request_id:
        job.meta["request_id"] = str(request_id).strip()
    job.save_meta()
    return QueueEnqueueResult(job_id=job.id, queue_name=queue.name)


def enqueue_problem_follow_up_job(
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
) -> QueueEnqueueResult:
    queue = get_analysis_queue()
    job = queue.enqueue(
        "app.services.platform_public_bridge.run_problem_follow_up_background",
        mode=mode,
        username=username,
        user_id=user_id,
        problem_payload=problem_payload,
        runtime_payload=runtime_payload,
        event_type=event_type,
        latency_ms=latency_ms,
        language=language,
        difficulty=difficulty,
        job_timeout=settings.ANALYSIS_QUEUE_JOB_TIMEOUT_SECONDS,
        result_ttl=settings.ANALYSIS_QUEUE_RESULT_TTL_SECONDS,
        failure_ttl=settings.ANALYSIS_QUEUE_FAILURE_TTL_SECONDS,
    )
    job.meta["user_id"] = int(user_id)
    job.meta["mode"] = str(mode or "").strip().lower()
    job.meta["username"] = str(username or "").strip()
    job.save_meta()
    return QueueEnqueueResult(job_id=job.id, queue_name=queue.name)

