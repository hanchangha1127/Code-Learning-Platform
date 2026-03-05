from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.core.config import settings
from app.db.models import Submission, SubmissionStatus, User
from app.schemas.analysis import AIAnalysisRead, AnalyzeStartResponse, SubmissionStatusResponse
from app.schemas.submission import SubmissionRead, SubmitRequest
from app.services.analysis_queue import enqueue_analysis_job, is_rq_enabled
from app.services.analysis_service import (
    get_submission_status,
    list_analyses_for_submission,
    run_analysis_background,
)
from app.services.submission_service import create_submission

router = APIRouter()


def _is_processing_stale(submission: Submission) -> bool:
    stale_seconds = max(int(settings.ANALYSIS_PROCESSING_STALE_SECONDS or 0), 0)
    if stale_seconds <= 0:
        return False

    started_at = submission.updated_at or submission.created_at
    if started_at is None:
        return False

    age_seconds = (datetime.utcnow() - started_at).total_seconds()
    return age_seconds >= stale_seconds


def _recover_stale_processing(db: Session, submission: Submission) -> bool:
    if submission.status != SubmissionStatus.processing:
        return False
    if not _is_processing_stale(submission):
        return False

    submission.status = SubmissionStatus.pending
    submission.score = None
    db.commit()
    db.refresh(submission)
    return True


@router.post("/problems/{problem_id}/submit", response_model=SubmissionRead)
def submit_problem(
    problem_id: int,
    body: SubmitRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        return create_submission(
            db=db,
            user_id=current.id,
            problem_id=problem_id,
            language=body.language,
            code=body.code,
        )
    except ValueError as exc:
        if str(exc) == "problem_not_found":
            raise HTTPException(status_code=404, detail="Problem not found") from exc
        raise


@router.post("/submissions/{submission_id}/analyze", response_model=AnalyzeStartResponse)
def analyze(
    submission_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        sub = db.query(Submission).filter(Submission.id == submission_id).with_for_update().first()

        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found")
        if sub.user_id != current.id:
            raise HTTPException(status_code=403, detail="Forbidden")

        if sub.status in (SubmissionStatus.passed, SubmissionStatus.failed):
            return {"analysis_id": submission_id, "message": "Already analyzed", "job_id": None}

        if sub.status == SubmissionStatus.error:
            return {
                "analysis_id": submission_id,
                "message": "Analysis previously failed",
                "job_id": None,
            }

        if sub.status == SubmissionStatus.processing and not _recover_stale_processing(db, sub):
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail="Analysis already in progress",
            )

        if sub.status != SubmissionStatus.pending:
            raise HTTPException(status_code=409, detail=f"Invalid status: {sub.status}")

        sub.status = SubmissionStatus.processing
        sub.score = None
        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    # Queue-first execution. If queue is disabled, fallback to in-process background task.
    if is_rq_enabled():
        try:
            enqueued = enqueue_analysis_job(submission_id=submission_id, user_id=current.id)
            return {
                "analysis_id": submission_id,
                "message": "Analysis queued",
                "job_id": enqueued.job_id,
            }
        except Exception as exc:
            try:
                sub = db.get(Submission, submission_id)
                if sub and sub.user_id == current.id and sub.status == SubmissionStatus.processing:
                    sub.status = SubmissionStatus.pending
                    sub.score = None
                    db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(
                status_code=503,
                detail="Failed to enqueue analysis job",
            ) from exc

    background_tasks.add_task(run_analysis_background, submission_id, current.id)
    return {"analysis_id": submission_id, "message": "Analysis started", "job_id": None}


@router.get("/submissions/{submission_id}/status", response_model=SubmissionStatusResponse)
def get_status(
    submission_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        sub, last, is_processing = get_submission_status(db, submission_id, current.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Submission not found") from exc

    if _recover_stale_processing(db, sub):
        is_processing = False

    return {
        "submission_id": sub.id,
        "status": sub.status.value if hasattr(sub.status, "value") else sub.status,
        "score": sub.score,
        "last_analysis": last,
        "is_processing": is_processing,
    }


@router.get("/submissions/{submission_id}/analyses", response_model=list[AIAnalysisRead])
def get_analyses(
    submission_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return list_analyses_for_submission(db, submission_id, current.id)
