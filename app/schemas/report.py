from __future__ import annotations

from pydantic import BaseModel, Field


class MilestoneReportRequest(BaseModel):
    problem_count: int = Field(default=10, ge=1, le=200)


class MetricSnapshot(BaseModel):
    attempts: int
    accuracy: float | None = None
    avgScore: float | None = None
    trend: str


class LearningSolutionReportRead(BaseModel):
    reportId: int | None
    createdAt: str
    goal: str
    solutionSummary: str
    priorityActions: list[str]
    phasePlan: list[str]
    dailyHabits: list[str]
    focusTopics: list[str]
    metricsToTrack: list[str]
    checkpoints: list[str]
    riskMitigation: list[str]
    metricSnapshot: MetricSnapshot

