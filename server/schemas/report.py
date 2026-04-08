from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MilestoneReportRequest(BaseModel):
    problem_count: int = Field(default=10, ge=1, le=200)


class LearningSolutionReportRead(BaseModel):
    status: str = "ready"
    reportId: int | None = None
    createdAt: str | None = None
    goal: str = ""
    solutionSummary: str = ""
    priorityActions: list[str] = Field(default_factory=list)
    phasePlan: list[str] = Field(default_factory=list)
    dailyHabits: list[str] = Field(default_factory=list)
    focusTopics: list[str] = Field(default_factory=list)
    metricsToTrack: list[str] = Field(default_factory=list)
    checkpoints: list[str] = Field(default_factory=list)
    riskMitigation: list[str] = Field(default_factory=list)
    metricSnapshot: dict[str, Any] = Field(default_factory=dict)
    reportBrief: dict[str, Any] = Field(default_factory=dict)
    pdfDownloadUrl: str | None = None
    currentAttemptCount: int | None = None
    minimumRequiredAttempts: int | None = None
    blockingMessage: str | None = None


class LatestLearningReportRead(BaseModel):
    available: bool
    reportId: int | None = None
    createdAt: str | None = None
    goal: str = ""
    summary: str = ""
    pdfDownloadUrl: str | None = None
