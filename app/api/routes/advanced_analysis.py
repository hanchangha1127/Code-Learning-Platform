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
from app.schemas.advanced_analysis import AdvancedAnalysisSubmitRequest
from app.services import platform_public_bridge
from app.services.platform_mode_observability import observe_platform_mode_operation
from server_runtime.schemas import ProblemRequest

router = APIRouter()


def _current_username(current: User) -> str:
    username = getattr(current, "username", None)
    if username:
        return str(username)
    return f"user_{getattr(current, 'id', 'unknown')}"


def _request_advanced_problem(
    *,
    request: Request,
    mode: str,
    body: ProblemRequest,
    db: Session,
    current: User,
):
    try:
        with observe_platform_mode_operation(mode=mode, operation="problem", user_id=current.id):
            if _wants_problem_stream(request):
                return _stream_problem_response(
                    request=request,
                    work=lambda emit_payload, emit_partial: _execute_stream_problem(
                        f"{mode}_problem",
                        lambda: platform_public_bridge.request_mode_problem(
                            mode=mode,
                            username=_current_username(current),
                            user_id=current.id,
                            language=body.language_id,
                            difficulty=body.difficulty_id,
                            db=None,
                            defer_persistence=True,
                            on_payload_ready=emit_payload,
                            on_partial_ready=emit_partial,
                        ),
                    ),
                )

            return platform_public_bridge.request_mode_problem(
                mode=mode,
                username=_current_username(current),
                user_id=current.id,
                language=body.language_id,
                difficulty=body.difficulty_id,
                db=db,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def submit_advanced_analysis_report(
    *,
    mode: str,
    current: User,
    body: AdvancedAnalysisSubmitRequest,
    db: Session,
) -> dict:
    return platform_public_bridge.submit_mode_answer(
        mode=mode,
        username=_current_username(current),
        user_id=current.id,
        body=body.model_dump(by_alias=True),
        db=db,
    )


@router.post("/single-file-analysis/problem")
def post_single_file_analysis_problem(
    body: ProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _request_advanced_problem(
        request=request,
        mode="single-file-analysis",
        body=body,
        db=db,
        current=current,
    )


@router.post("/multi-file-analysis/problem")
def post_multi_file_analysis_problem(
    body: ProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _request_advanced_problem(
        request=request,
        mode="multi-file-analysis",
        body=body,
        db=db,
        current=current,
    )


@router.post("/fullstack-analysis/problem")
def post_fullstack_analysis_problem(
    body: ProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _request_advanced_problem(
        request=request,
        mode="fullstack-analysis",
        body=body,
        db=db,
        current=current,
    )


@router.post("/single-file-analysis/submit")
def post_single_file_analysis_submit(
    body: AdvancedAnalysisSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        with observe_platform_mode_operation(mode="single-file-analysis", operation="submit", user_id=current.id):
            return execute_platform_mode_submit(
                mode="single-file-analysis",
                user_id=current.id,
                payload={
                    "problem_id": body.problem_id,
                    "report": body.report,
                },
                inline_submit=lambda: submit_advanced_analysis_report(
                    mode="single-file-analysis",
                    current=current,
                    body=body,
                    db=db,
                ),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/multi-file-analysis/submit")
def post_multi_file_analysis_submit(
    body: AdvancedAnalysisSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        with observe_platform_mode_operation(mode="multi-file-analysis", operation="submit", user_id=current.id):
            return execute_platform_mode_submit(
                mode="multi-file-analysis",
                user_id=current.id,
                payload={
                    "problem_id": body.problem_id,
                    "report": body.report,
                },
                inline_submit=lambda: submit_advanced_analysis_report(
                    mode="multi-file-analysis",
                    current=current,
                    body=body,
                    db=db,
                ),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fullstack-analysis/submit")
def post_fullstack_analysis_submit(
    body: AdvancedAnalysisSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        with observe_platform_mode_operation(mode="fullstack-analysis", operation="submit", user_id=current.id):
            return execute_platform_mode_submit(
                mode="fullstack-analysis",
                user_id=current.id,
                payload={
                    "problem_id": body.problem_id,
                    "report": body.report,
                },
                inline_submit=lambda: submit_advanced_analysis_report(
                    mode="fullstack-analysis",
                    current=current,
                    body=body,
                    db=db,
                ),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
