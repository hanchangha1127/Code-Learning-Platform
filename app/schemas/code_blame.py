from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

CodeBlameDifficulty = Literal["beginner", "intermediate", "advanced"]
CodeBlameOptionId = Literal["A", "B", "C", "D", "E"]
CodeBlameVerdict = Literal["passed", "failed"]


class CodeBlameProblemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    language: str = Field(..., min_length=1, max_length=32)
    difficulty: str = Field(..., min_length=1, max_length=32)


class CodeBlameCommit(BaseModel):
    optionId: CodeBlameOptionId
    title: str
    diff: str


class CodeBlameCommitReview(BaseModel):
    optionId: CodeBlameOptionId
    summary: str


class CodeBlameProblemResponse(BaseModel):
    problemId: str = Field(..., min_length=1, max_length=128)
    title: str
    language: str
    difficulty: CodeBlameDifficulty
    errorLog: str
    commits: list[CodeBlameCommit]
    prompt: str
    decisionFacets: list[str]


class CodeBlameSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    selected_commits: list[str] = Field(
        ...,
        validation_alias=AliasChoices("selectedCommits", "selected_commits"),
        min_length=1,
        max_length=2,
    )
    report: str

    @field_validator("selected_commits")
    @classmethod
    def _normalize_selected_commits(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for entry in value:
            token = str(entry or "").strip().upper()
            if token not in {"A", "B", "C", "D", "E"}:
                raise ValueError("selectedCommits must contain only A, B, C, D, E")
            if token in normalized:
                raise ValueError("selectedCommits must not contain duplicates")
            normalized.append(token)
        if not normalized:
            raise ValueError("selectedCommits must not be empty")
        if len(normalized) > 2:
            raise ValueError("selectedCommits must contain up to 2 commits")
        return normalized


class CodeBlameFeedback(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]


class CodeBlameSubmitResponse(BaseModel):
    correct: bool
    score: float
    verdict: CodeBlameVerdict
    feedback: CodeBlameFeedback
    foundTypes: list[str]
    missedTypes: list[str]
    referenceReport: str
    passThreshold: int = 70
    selectedCommits: list[CodeBlameOptionId]
    culpritCommits: list[CodeBlameOptionId]
    commitReviews: list[CodeBlameCommitReview]
