from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

AuditorDifficulty = Literal["beginner", "intermediate", "advanced"]
AuditorVerdict = Literal["passed", "failed"]


class AuditorProblemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    language: str = Field(..., min_length=1, max_length=32)
    difficulty: str = Field(..., min_length=1, max_length=32)


class AuditorProblemResponse(BaseModel):
    problemId: str = Field(..., min_length=1, max_length=128)
    title: str
    language: str
    difficulty: AuditorDifficulty
    code: str
    prompt: str
    trapCount: int


class AuditorSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    report: str = Field(..., min_length=1, max_length=8000)


class AuditorFeedback(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]


class AuditorSubmitResponse(BaseModel):
    correct: bool
    score: float
    verdict: AuditorVerdict
    feedback: AuditorFeedback
    foundTypes: list[str]
    missedTypes: list[str]
    referenceReport: str
    passThreshold: int = 70
