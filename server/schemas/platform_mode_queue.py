from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlatformModeSubmitQueuedResponse(BaseModel):
    queued: bool = True
    message: str
    jobId: str


class PlatformModeSubmitJobStatusResponse(BaseModel):
    jobId: str
    status: Literal["queued", "started", "finished", "failed", "not_found"]
    queued: bool
    finished: bool
    failed: bool
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=300)
