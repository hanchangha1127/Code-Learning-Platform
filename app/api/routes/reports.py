from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.db.models import User
from app.schemas.report import LearningSolutionReportRead, MilestoneReportRequest
from app.services.report_service import create_milestone_report

router = APIRouter()


@router.post("/reports/milestone", response_model=LearningSolutionReportRead)
def post_milestone_report(
    body: MilestoneReportRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if body.problem_count < 1 or body.problem_count > 200:
        raise HTTPException(status_code=400, detail="problem_count must be 1..200")

    try:
        report_payload = create_milestone_report(db, current.id, body.problem_count)
    except RuntimeError as exc:
        if "learning_report_generation_failed" in str(exc):
            raise HTTPException(
                status_code=503,
                detail="학습 리포트 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            ) from exc
        raise
    return report_payload
