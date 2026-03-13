from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LearningGoalUpdate(BaseModel):
    daily_target_sessions: int = Field(ge=1, le=70)
    focus_modes: list[str] = Field(default_factory=list)
    focus_topics: list[str] = Field(default_factory=list)


class LearningGoalRead(BaseModel):
    dailyTargetSessions: int
    focusModes: list[str]
    focusTopics: list[str]
    updatedAt: str | None = None


class ReviewQueueItemRead(BaseModel):
    id: int
    mode: str
    modeLabel: str
    title: str
    weaknessTag: str | None = None
    weaknessLabel: str | None = None
    dueAt: str | None = None
    priority: int
    actionLink: str
    resumeLink: str
    sourceProblemId: str | None = None


class ReviewQueueRead(BaseModel):
    dueCount: int
    items: list[ReviewQueueItemRead]


class DailyGoalProgressRead(BaseModel):
    date: str
    targetSessions: int
    completedSessions: int
    remainingSessions: int
    progressPercent: float
    achieved: bool


class TrendSnapshotRead(BaseModel):
    last7DaysAttempts: int
    last30DaysAttempts: int
    last7DaysAccuracy: float | None = None
    last30DaysAccuracy: float | None = None


class LearningTaskRead(BaseModel):
    type: Literal["review", "practice", "focus"]
    title: str
    description: str
    actionLabel: str
    actionLink: str


class RecommendedModeRead(BaseModel):
    mode: str
    label: str
    link: str


class WeeklyReportCardRead(BaseModel):
    available: bool
    reportId: int | None = None
    createdAt: str | None = None
    goal: str = ""
    solutionSummary: str = ""
    actionLink: str
    stale: bool = False


class NotificationRead(BaseModel):
    type: str
    severity: Literal["info", "warn", "urgent"]
    title: str
    description: str
    actionLabel: str
    actionLink: str
    count: int = 0


class ReviewResumeRead(BaseModel):
    reviewItemId: int
    mode: str
    resumeLink: str
    problem: dict


class LearningHomeRead(BaseModel):
    displayName: str
    todayDate: str
    streakDays: int
    skillLevel: str
    dailyGoal: DailyGoalProgressRead
    reviewQueue: ReviewQueueRead
    todayTasks: list[LearningTaskRead]
    weakTopics: list[str]
    recommendedModes: list[RecommendedModeRead]
    trend: TrendSnapshotRead
    stats: dict[str, float | int | None]
    focusModes: list[str]
    focusTopics: list[str]
    weeklyReportCard: WeeklyReportCardRead
    notifications: list[NotificationRead]
