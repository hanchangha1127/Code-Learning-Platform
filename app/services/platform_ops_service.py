from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.request_context import get_request_id
from app.db.models import PlatformOpsEvent


def record_ops_event(
    db: Session | None,
    *,
    user_id: int | None,
    event_type: str,
    mode: str | None = None,
    status: str | None = None,
    latency_ms: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if db is None or not all(hasattr(db, attr) for attr in ("add", "flush")):
        return

    db.add(
        PlatformOpsEvent(
            user_id=user_id,
            request_id=get_request_id(),
            event_type=str(event_type or "unknown")[:80],
            mode=(str(mode).strip().lower()[:50] if mode else None),
            status=(str(status).strip().lower()[:40] if status else None),
            latency_ms=latency_ms,
            payload=payload or None,
        )
    )
