from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

ContextInferenceDifficulty = Literal["beginner", "intermediate", "advanced"]
ContextInferenceType = Literal["pre_condition", "post_condition"]
ContextInferenceVerdict = Literal["passed", "failed"]


class ContextInferenceProblemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    language: str = Field(..., min_length=1, max_length=32)
    difficulty: str = Field(..., min_length=1, max_length=32)


class ContextInferenceProblemResponse(BaseModel):
    problemId: str = Field(..., min_length=1, max_length=128)
    title: str
    language: str
    difficulty: ContextInferenceDifficulty
    snippet: str
    prompt: str
    inferenceType: ContextInferenceType


class ContextInferenceSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    report: str = Field(..., min_length=1, max_length=8000)


class ContextInferenceFeedback(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]


class ContextInferenceSubmitResponse(BaseModel):
    correct: bool
    score: float
    verdict: ContextInferenceVerdict
    feedback: ContextInferenceFeedback
    foundTypes: list[str]
    missedTypes: list[str]
    referenceReport: str
    passThreshold: int = 70
