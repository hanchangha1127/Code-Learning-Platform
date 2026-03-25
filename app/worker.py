from __future__ import annotations

import os
import time

from redis import Redis
from rq import Worker

from app.core.config import settings


def _build_redis_connection() -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        socket_connect_timeout=3,
        socket_timeout=5,
        decode_responses=False,
    )


def _wait_for_redis(timeout_seconds: int = 120) -> Redis:
    deadline = time.time() + timeout_seconds
    while True:
        conn = _build_redis_connection()
        try:
            conn.ping()
            return conn
        except Exception as exc:
            if time.time() >= deadline:
                raise RuntimeError(f"Redis wait timeout: {exc}") from exc
            time.sleep(2)


def _worker_queue_names() -> list[str]:
    configured = os.getenv("RQ_WORKER_QUEUES")
    if configured:
        candidates = [item.strip() for item in configured.split(",") if item.strip()]
    else:
        candidates: list[str] = []
        if (settings.PROBLEM_FOLLOW_UP_QUEUE_MODE or "inline").lower() == "rq":
            candidates.append(str(settings.PROBLEM_FOLLOW_UP_QUEUE_NAME or "").strip())
        if (settings.ANALYSIS_QUEUE_MODE or "inline").lower() == "rq":
            candidates.append(str(settings.ANALYSIS_QUEUE_NAME or "").strip())

    queue_names: list[str] = []
    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        queue_names.append(name)
    return queue_names or [settings.ANALYSIS_QUEUE_NAME]


def main() -> None:
    conn = _wait_for_redis()
    worker = Worker(_worker_queue_names(), connection=conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
