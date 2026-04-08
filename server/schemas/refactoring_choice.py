from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

RefactoringChoiceDifficulty = Literal["beginner", "intermediate", "advanced"]
RefactoringChoiceOptionId = Literal["A", "B", "C"]
RefactoringChoiceVerdict = Literal["passed", "failed"]


class RefactoringChoiceProblemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    language: str = Field(..., min_length=1, max_length=32)
    difficulty: str = Field(..., min_length=1, max_length=32)


class RefactoringChoiceOption(BaseModel):
    optionId: RefactoringChoiceOptionId
    title: str
    code: str


class RefactoringChoiceOptionReview(BaseModel):
    optionId: RefactoringChoiceOptionId
    summary: str


class RefactoringChoiceProblemResponse(BaseModel):
    problemId: str = Field(..., min_length=1, max_length=128)
    title: str
    language: str
    difficulty: RefactoringChoiceDifficulty
    scenario: str
    constraints: list[str]
    options: list[RefactoringChoiceOption]
    prompt: str
    decisionFacets: list[str]


class RefactoringChoiceSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    selected_option: str = Field(
        ...,
        validation_alias=AliasChoices("selectedOption", "selected_option"),
        min_length=1,
        max_length=8,
    )
    report: str = Field(..., min_length=1, max_length=8000)

    @field_validator("selected_option")
    @classmethod
    def _normalize_selected_option(cls, value: str) -> str:
        return str(value or "").strip().upper()


class RefactoringChoiceFeedback(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]


class RefactoringChoiceSubmitResponse(BaseModel):
    correct: bool
    score: float
    verdict: RefactoringChoiceVerdict
    feedback: RefactoringChoiceFeedback
    foundTypes: list[str]
    missedTypes: list[str]
    referenceReport: str
    passThreshold: int = 70
    selectedOption: RefactoringChoiceOptionId
    bestOption: RefactoringChoiceOptionId
    optionReviews: list[RefactoringChoiceOptionReview]
