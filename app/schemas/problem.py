from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel

from app.db.models import ProblemKind, ProblemDifficulty


class ProblemRead(BaseModel):
    id: int
    kind: ProblemKind
    title: str
    description: str
    difficulty: ProblemDifficulty
    language: str
    starter_code: str | None
    options: dict | list | None
    #answer_index: int | None
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProblemListResponse(BaseModel):
    items: list[ProblemRead]
    total: int
    limit: int
    offset: int
