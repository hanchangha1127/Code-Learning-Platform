# app/db/models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


# ------------------------
# Enums (matching DB ENUM values)
# ------------------------

class UserRole(str, Enum):
    user = "user"
    admin = "admin"


class UserStatus(str, Enum):
    active = "active"
    blocked = "blocked"
    deleted = "deleted"


class PreferredDifficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class ProblemKind(str, Enum):
    coding = "coding"
    code_block = "code_block"
    auditor = "auditor"
    context_inference = "context_inference"
    refactoring_choice = "refactoring_choice"
    code_blame = "code_blame"


class ProblemDifficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class SubmissionStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    passed = "passed"
    failed = "failed"
    error = "error"


class AnalysisType(str, Enum):
    error = "error"
    review = "review"
    hint = "hint"
    explain = "explain"


class ReportType(str, Enum):
    weekly = "weekly"
    monthly = "monthly"
    milestone = "milestone"


# ------------------------
# Tables
# ------------------------

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        server_default=UserRole.user.value,
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"),
        nullable=False,
        server_default=UserStatus.active.value,
    )

    # Relationships
    settings: Mapped["UserSettings"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    created_problems: Mapped[list["Problem"]] = relationship(
        back_populates="creator",
        foreign_keys="Problem.created_by",
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    analyses: Mapped[list["AIAnalysis"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    problem_stats: Mapped[list["UserProblemStat"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserSettings(TimestampMixin, Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    preferred_language: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="python",
    )
    preferred_difficulty: Mapped[PreferredDifficulty] = mapped_column(
        SAEnum(PreferredDifficulty, name="preferred_difficulty"),
        nullable=False,
        server_default=PreferredDifficulty.medium.value,
    )

    user: Mapped["User"] = relationship(back_populates="settings")


class UserSession(TimestampMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        sa.Index("ix_user_sessions_refresh_token_hash", "refresh_token_hash"),
        sa.Index("ix_user_sessions_active_lookup", "refresh_token_hash", "revoked_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Problem(TimestampMixin, Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    kind: Mapped[ProblemKind] = mapped_column(
        SAEnum(ProblemKind, name="problem_kind"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    difficulty: Mapped[ProblemDifficulty] = mapped_column(
        SAEnum(ProblemDifficulty, name="problem_difficulty"),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(30), nullable=False)

    starter_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Code-block problem options and answer index.
    options: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    answer_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Reference solution (not exposed by default in public APIs).
    reference_solution: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="1"
    )

    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    creator: Mapped["User | None"] = relationship(
        back_populates="created_problems",
        foreign_keys=[created_by],
    )

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
    )
    stats: Mapped[list["UserProblemStat"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
    )


class Submission(TimestampMixin, Base):
    __tablename__ = "submissions"
    __table_args__ = (
        sa.Index("ix_submissions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    problem_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    language: Mapped[str] = mapped_column(String(30), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, name="submission_status"),
        nullable=False,
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship(back_populates="submissions")
    problem: Mapped["Problem"] = relationship(back_populates="submissions")

    analyses: Mapped[list["AIAnalysis"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class AIAnalysis(TimestampMixin, Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        sa.Index("ix_ai_analyses_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    submission_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    analysis_type: Mapped[AnalysisType] = mapped_column(
        SAEnum(AnalysisType, name="analysis_type"),
        nullable=False,
    )

    result_summary: Mapped[str] = mapped_column(Text, nullable=False)
    result_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="analyses")
    submission: Mapped["Submission | None"] = relationship(back_populates="analyses")


class UserProblemStat(Base):
    __tablename__ = "user_problem_stats"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    problem_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("problems.id", ondelete="CASCADE"),
        primary_key=True,
    )

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    best_status: Mapped[SubmissionStatus | None] = mapped_column(
        SAEnum(SubmissionStatus, name="best_status"),
        nullable=True,
    )
    best_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Per-problem wrong answer analysis payload.
    # Example:
    # {
    #   "total_wrong": 4,
    #   "types": {"logic_error": 2, "runtime_error": 1, "syntax_error": 1},
    #   "last_wrong_type": "logic_error",
    #   "last_wrong_at": "2026-02-09T12:34:56"
    # }
    wrong_answer_types: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    last_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="problem_stats")
    problem: Mapped["Problem"] = relationship(back_populates="stats")


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        sa.Index("ix_reports_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    report_type: Mapped[ReportType] = mapped_column(
        SAEnum(ReportType, name="report_type"),
        nullable=False,
    )

    period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    milestone_problem_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    strengths: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    weaknesses: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    stats: Mapped[dict | list] = mapped_column(JSON, nullable=False)

    user: Mapped["User"] = relationship(back_populates="reports")

