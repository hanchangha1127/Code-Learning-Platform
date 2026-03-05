from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.db.models import SubmissionStatus

LanguageStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=30,
        pattern=r"^[A-Za-z0-9_+#.-]+$",
    ),
]


class SubmitRequest(BaseModel):
    language: LanguageStr
    code: Annotated[str, StringConstraints(min_length=1, max_length=50000)]

    @field_validator("code")
    @classmethod
    def validate_code_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value


class SubmissionRead(BaseModel):
    id: int
    user_id: int
    problem_id: int
    language: str
    status: SubmissionStatus
    score: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
