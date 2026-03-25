from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.problem_streaming import (
    _execute_stream_problem,
    _stream_problem_response,
    _wants_problem_stream,
)
from app.api.routes.platform_mode_queue import execute_platform_mode_submit
from app.api.security_deps import get_current_user
from app.db.models import User
from app.schemas.auditor import AuditorProblemRequest, AuditorSubmitRequest
from app.services import platform_public_bridge
from app.services.platform_mode_observability import observe_platform_mode_operation

router = APIRouter()


def _current_username(current: User) -> str:
    username = getattr(current, "username", None)
    if username:
        return str(username)
    return f"user_{getattr(current, 'id', 'unknown')}"


def submit_auditor_report(*, current: User, body: AuditorSubmitRequest, db: Session) -> dict:
    return platform_public_bridge.submit_mode_answer(
        mode="auditor",
        username=_current_username(current),
        user_id=current.id,
        body=body.model_dump(by_alias=True),
        db=db,
    )


@router.post("/problem")
def post_auditor_problem(
    body: AuditorProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        with observe_platform_mode_operation(mode="auditor", operation="problem", user_id=current.id):
            if _wants_problem_stream(request):
                return _stream_problem_response(
                    request=request,
                    work=lambda emit_payload, emit_partial: _execute_stream_problem(
                        "auditor_problem",
                        lambda: platform_public_bridge.request_mode_problem(
                            mode="auditor",
                            username=_current_username(current),
                            user_id=current.id,
                            language=body.language,
                            difficulty=body.difficulty,
                            db=None,
                            defer_persistence=True,
                            on_payload_ready=emit_payload,
                            on_partial_ready=emit_partial,
                        ),
                    ),
                )
            return platform_public_bridge.request_mode_problem(
                mode="auditor",
                username=_current_username(current),
                user_id=current.id,
                language=body.language,
                difficulty=body.difficulty,
                db=db,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/submit")
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
                inline_submit=lambda: submit_auditor_report(current=current, body=body, db=db),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
