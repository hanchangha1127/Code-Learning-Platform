from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class TokenResponse(BaseModel):
    token: str


class DiagnosticStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    language_id: str = Field(
        ...,
        validation_alias=AliasChoices("languageId", "language"),
        min_length=1,
        max_length=32,
    )
    difficulty: str = Field(..., min_length=1, max_length=32)


class ProblemRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    language_id: str = Field(
        default="python",
        validation_alias=AliasChoices("language", "languageId"),
        min_length=1,
        max_length=32,
    )
    difficulty_id: str = Field(
        default="beginner",
        validation_alias=AliasChoices("difficulty", "difficultyId"),
        min_length=1,
        max_length=32,
    )


class ExplanationSubmission(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    language_id: str = Field(
        ...,
        validation_alias=AliasChoices("language", "languageId"),
        min_length=1,
        max_length=32,
    )
    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    explanation: str = Field(..., min_length=1, max_length=8000)


class CodeBlockSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    selected_option: int = Field(
        ...,
        validation_alias=AliasChoices("selectedOption", "selected_option"),
        ge=0,
    )


class CodeArrangeSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    order: list[str] = Field(..., min_length=1, max_length=256)

    @field_validator("order")
    @classmethod
    def _validate_order(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("order 배열에는 빈 문자열이 포함될 수 없습니다.")
        return cleaned


class AuditorSubmitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)
    problem_id: str = Field(
        ...,
        validation_alias=AliasChoices("problemId", "problem_id"),
        min_length=1,
        max_length=128,
    )
    report: str = Field(..., min_length=1, max_length=8000)


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
    report: str = Field(..., min_length=1, max_length=8000)

    @field_validator("selected_commits")
    @classmethod
    def _normalize_selected_commits(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("selectedCommits는 배열이어야 합니다.")

        normalized: list[str] = []
        for entry in value:
            token = str(entry or "").strip().upper()
            if token not in {"A", "B", "C", "D", "E"}:
                raise ValueError("selectedCommits는 A~E 중에서만 선택할 수 있습니다.")
            if token in normalized:
                raise ValueError("selectedCommits에 중복 항목을 포함할 수 없습니다.")
            normalized.append(token)
        if not normalized:
            raise ValueError("selectedCommits를 최소 1개 선택해야 합니다.")
        if len(normalized) > 2:
            raise ValueError("selectedCommits는 최대 2개까지 선택할 수 있습니다.")
        return normalized
