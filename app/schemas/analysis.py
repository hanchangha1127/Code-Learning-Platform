from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db.models import AnalysisType, SubmissionStatus


class AnalyzeStartResponse(BaseModel):
    analysis_id: int
    message: str
    job_id: str | None = None


class AIAnalysisRead(BaseModel):
    id: int
    user_id: int
    submission_id: int | None
    analysis_type: AnalysisType
    result_summary: str
    result_detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIAnalysisSummary(BaseModel):
    id: int
    analysis_type: AnalysisType
    result_summary: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SubmissionStatusResponse(BaseModel):
    submission_id: int
    status: SubmissionStatus
    score: int | None
    last_analysis: AIAnalysisSummary | None
    is_processing: bool

    model_config = {"from_attributes": True}
