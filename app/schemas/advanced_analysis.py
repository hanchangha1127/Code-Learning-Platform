from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

AdvancedAnalysisVerdict = Literal["passed", "failed"]


class AdvancedAnalysisSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    report: str = Field(..., min_length=1, max_length=12000)


class AdvancedAnalysisFeedback(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]


class AdvancedAnalysisSubmitResponse(BaseModel):
    correct: bool
    score: float
    verdict: AdvancedAnalysisVerdict
    feedback: AdvancedAnalysisFeedback
    referenceReport: str
    passThreshold: int = 70
