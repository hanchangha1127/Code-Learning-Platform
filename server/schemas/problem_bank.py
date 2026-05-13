from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProblemBankItemRead(BaseModel):
    id: int
    title: str
    mode: str
    mode_label: str
    language: str
    difficulty: str
    submissions: int
    success_rate: float | None
    my_status: str
    created_at: datetime
    updated_at: datetime
    solve_link: str


class ProblemBankSummaryRead(BaseModel):
    total_problems: int
    total_submissions: int
    solved_count: int
    tried_count: int
    average_success_rate: float | None


class ProblemBankListRead(BaseModel):
    items: list[ProblemBankItemRead]
    summary: ProblemBankSummaryRead
    total: int
    limit: int
    offset: int


class ProblemBankResumeRead(BaseModel):
    bank_problem_id: int
    mode: str
    mode_label: str
    resume_link: str
    problem: dict[str, Any]
