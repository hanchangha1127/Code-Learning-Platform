from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.platform_mode_queue import execute_platform_mode_submit
from app.api.security_deps import get_current_user
from app.db.models import User
from app.schemas.code_blame import (
    CodeBlameProblemRequest,
    CodeBlameProblemResponse,
    CodeBlameSubmitRequest,
    CodeBlameSubmitResponse,
)
from app.schemas.platform_mode_queue import PlatformModeSubmitQueuedResponse
from app.services.platform_mode_observability import observe_platform_mode_operation
from app.services.code_blame_service import create_code_blame_problem, submit_code_blame_report

router = APIRouter()


@router.post("/problem", response_model=CodeBlameProblemResponse)
def post_code_blame_problem(
    body: CodeBlameProblemRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        with observe_platform_mode_operation(mode="code-blame", operation="problem", user_id=current.id):
            return create_code_blame_problem(
                db,
                user_id=current.id,
                language=body.language,
                difficulty=body.difficulty,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/submit", response_model=CodeBlameSubmitResponse | PlatformModeSubmitQueuedResponse)
def post_code_blame_submit(
    body: CodeBlameSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        with observe_platform_mode_operation(mode="code-blame", operation="submit", user_id=current.id):
            return execute_platform_mode_submit(
                mode="code-blame",
                user_id=current.id,
                payload={
                    "problem_id": body.problem_id,
                    "selected_commits": body.selected_commits,
                    "report": body.report,
                },
                inline_submit=lambda: submit_code_blame_report(
                    db,
                    user_id=current.id,
                    problem_id=body.problem_id,
                    selected_commits=body.selected_commits,
                    report=body.report,
                ),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
