from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.db.models import User
from app.schemas.learning_continuity import LearningHomeRead, ReviewQueueRead, ReviewResumeRead
from app.services.learning_continuity_service import (
    build_learning_home,
    list_due_review_queue,
    resume_review_queue_item,
)
from app.services import platform_public_bridge
from server_runtime.routes.learning import (
    _execute_stream_problem,
    _stream_problem_response,
    _wants_problem_stream,
)
from server_runtime.schemas import (
    CodeArrangeSubmitRequest,
    CodeBlockSubmitRequest,
    CodeCalcSubmitRequest,
    CodeErrorSubmitRequest,
    ExplanationSubmission,
    ProblemRequest,
)

router = APIRouter()

LEARNING_REPORT_FAILURE_DETAIL = "학습 리포트 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."


@router.get("/languages")
def get_languages() -> dict:
    return {"languages": platform_public_bridge.list_public_languages()}


@router.get("/profile")
def get_profile(current: User = Depends(get_current_user)) -> dict:
    return platform_public_bridge.get_public_profile(current.username)


@router.get("/home", response_model=LearningHomeRead)
def get_home(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    history = platform_public_bridge.get_public_history(current.username)
    profile = platform_public_bridge.get_public_profile(current.username, history=history)
    me = platform_public_bridge.get_public_me(current)
    return build_learning_home(
        db=db,
        user=current,
        history=history,
        profile=profile,
        display_name=me.get("displayName") or me.get("display_name") or current.username,
    )


@router.get("/report")
def get_report(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    try:
        return platform_public_bridge.get_public_report(current.username, current.id, db)
    except RuntimeError as exc:
        if "learning_report_generation_failed" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=LEARNING_REPORT_FAILURE_DETAIL,
            ) from exc
        raise


@router.get("/learning/history")
def get_history(current: User = Depends(get_current_user)) -> dict:
    return {"history": platform_public_bridge.get_public_history(current.username)}


@router.get("/learning/memory")
def get_memory(current: User = Depends(get_current_user)) -> dict:
    return {"memory": platform_public_bridge.get_public_memory(current.username)}


@router.get("/learning/review-queue", response_model=ReviewQueueRead)
def get_review_queue(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    items = list_due_review_queue(db, current.id)
    return {
        "dueCount": len(items),
        "items": items,
    }


@router.get("/review-queue/{item_id}/resume", response_model=ReviewResumeRead)
def get_review_queue_resume(
    item_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    try:
        return resume_review_queue_item(db, current.id, item_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="복습할 문제를 찾지 못했습니다.") from exc


def _request_problem_with_optional_stream(
    *,
    request: Request,
    mode: str,
    body: ProblemRequest,
    db: Session,
    current: User,
):
    if _wants_problem_stream(request):
        return _stream_problem_response(
            request=request,
            work=lambda: _execute_stream_problem(
                f"{mode}_problem",
                lambda: platform_public_bridge.request_mode_problem(
                    mode=mode,
                    username=current.username,
                    user_id=current.id,
                    language=body.language_id,
                    difficulty=body.difficulty_id,
                    db=None,
                ),
            ),
        )

    try:
        return platform_public_bridge.request_mode_problem(
            mode=mode,
            username=current.username,
            user_id=current.id,
            language=body.language_id,
            difficulty=body.difficulty_id,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _submit_mode(
    *,
    mode: str,
    body: dict,
    db: Session,
    current: User,
) -> dict:
    try:
        return platform_public_bridge.submit_mode_answer(
            mode=mode,
            username=current.username,
            user_id=current.id,
            body=body,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/analysis/problem")
def post_analysis_problem(
    body: ProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _request_problem_with_optional_stream(request=request, mode="analysis", body=body, db=db, current=current)


@router.post("/analysis/submit")
def post_analysis_submit(
    body: ExplanationSubmission,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    return _submit_mode(mode="analysis", body=body.model_dump(by_alias=True), db=db, current=current)


@router.post("/codeblock/problem")
def post_code_block_problem(
    body: ProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _request_problem_with_optional_stream(request=request, mode="code-block", body=body, db=db, current=current)


@router.post("/codeblock/submit")
def post_code_block_submit(
    body: CodeBlockSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    return _submit_mode(mode="code-block", body=body.model_dump(by_alias=True), db=db, current=current)


@router.post("/arrange/problem")
def post_code_arrange_problem(
    body: ProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _request_problem_with_optional_stream(request=request, mode="code-arrange", body=body, db=db, current=current)


@router.post("/arrange/submit")
def post_code_arrange_submit(
    body: CodeArrangeSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    return _submit_mode(mode="code-arrange", body=body.model_dump(by_alias=True), db=db, current=current)


@router.post("/codecalc/problem")
def post_code_calc_problem(
    body: ProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _request_problem_with_optional_stream(request=request, mode="code-calc", body=body, db=db, current=current)


@router.post("/codecalc/submit")
def post_code_calc_submit(
    body: CodeCalcSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    return _submit_mode(mode="code-calc", body=body.model_dump(by_alias=True), db=db, current=current)


@router.post("/codeerror/problem")
def post_code_error_problem(
    body: ProblemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return _request_problem_with_optional_stream(request=request, mode="code-error", body=body, db=db, current=current)


@router.post("/codeerror/submit")
def post_code_error_submit(
    body: CodeErrorSubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    return _submit_mode(mode="code-error", body=body.model_dump(by_alias=True), db=db, current=current)
