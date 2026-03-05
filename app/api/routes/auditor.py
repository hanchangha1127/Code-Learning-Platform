from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.api.routes.platform_mode_queue import execute_platform_mode_submit
from app.db.models import User
from app.schemas.auditor import (
    AuditorProblemRequest,
    AuditorProblemResponse,
    AuditorSubmitRequest,
    AuditorSubmitResponse,
)
from app.schemas.platform_mode_queue import PlatformModeSubmitQueuedResponse
from app.services.platform_mode_observability import observe_platform_mode_operation
from app.services.auditor_service import create_auditor_problem, submit_auditor_report

router = APIRouter()


@router.post("/problem", response_model=AuditorProblemResponse)
def post_auditor_problem(
    body: AuditorProblemRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        with observe_platform_mode_operation(mode="auditor", operation="problem", user_id=current.id):
            return create_auditor_problem(
                db,
                user_id=current.id,
                language=body.language,
                difficulty=body.difficulty,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/submit", response_model=AuditorSubmitResponse | PlatformModeSubmitQueuedResponse)
def post_auditor_submit(
    body: AuditorSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        with observe_platform_mode_operation(mode="auditor", operation="submit", user_id=current.id):
            return execute_platform_mode_submit(
                mode="auditor",
                user_id=current.id,
                payload={
                    "problem_id": body.problem_id,
                    "report": body.report,
                },
                inline_submit=lambda: submit_auditor_report(
                    db,
                    user_id=current.id,
                    problem_id=body.problem_id,
                    report=body.report,
                ),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
