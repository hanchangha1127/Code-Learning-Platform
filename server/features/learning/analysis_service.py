from __future__ import annotations

from sqlalchemy.orm import Session

from server.db.models import AIAnalysis, AnalysisType, Submission, SubmissionStatus
from server.db.session import SessionLocal
from server.features.learning.analysis_core import analyze_submission
from server.features.learning.problem_stat_service import update_user_problem_stat


def run_analysis_background(submission_id: int, user_id: int) -> None:
    db: Session = SessionLocal()
    try:
        analyze_submission(db, submission_id, user_id)
        db.commit()

    except Exception as exc:
        db.rollback()

        # Record terminal error status and persist a diagnostic analysis row.
        try:
            sub = db.get(Submission, submission_id)
            if sub and sub.user_id == user_id:
                sub.status = SubmissionStatus.error
                sub.score = None

                db.add(
                    AIAnalysis(
                        user_id=user_id,
                        submission_id=submission_id,
                        analysis_type=AnalysisType.review,
                        result_summary="analysis_error",
                        result_detail=str(exc)[:1000],
                    )
                )

                update_user_problem_stat(
                    db=db,
                    user_id=user_id,
                    problem_id=sub.problem_id,
                    score=None,
                    status=SubmissionStatus.error,
                    analysis_summary="analysis_error",
                    analysis_detail=str(exc),
                )
                db.commit()
        except Exception:
            db.rollback()

    finally:
        db.close()


def get_submission_status(db: Session, submission_id: int, user_id: int):
    sub = db.get(Submission, submission_id)
    if not sub or sub.user_id != user_id:
        raise ValueError("submission_not_found")

    last = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.user_id == user_id, AIAnalysis.submission_id == submission_id)
        .order_by(AIAnalysis.id.desc())
        .first()
    )

    is_processing = sub.status == SubmissionStatus.processing
    return sub, last, is_processing


def list_analyses_for_submission(
    db: Session,
    submission_id: int,
    user_id: int,
):
    sub = db.get(Submission, submission_id)
    if not sub or sub.user_id != user_id:
        raise ValueError("submission_not_found")

    return (
        db.query(AIAnalysis)
        .filter(
            AIAnalysis.user_id == user_id,
            AIAnalysis.submission_id == submission_id,
        )
        .order_by(AIAnalysis.id.desc())
        .all()
    )
