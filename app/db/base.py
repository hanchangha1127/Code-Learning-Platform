# app/db/base.py
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    # MySQL DATETIME은 timezone을 저장하지 않으니 naive로 넣음
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )
