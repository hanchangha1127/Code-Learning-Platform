from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models import ReportType


class MilestoneReportRequest(BaseModel):
    problem_count: int = Field(default=10, ge=1, le=200)


class ReportRead(BaseModel):
    id: int
    user_id: int
    report_type: ReportType

    period_start: datetime | None
    period_end: datetime | None
    milestone_problem_count: int | None

    title: str
    summary: str

    strengths: list[str] | None
    weaknesses: list[str] | None
    recommendations: list[str] | None

    stats: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
