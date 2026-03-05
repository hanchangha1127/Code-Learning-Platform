from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.db.models import User
from app.schemas.report import MilestoneReportRequest, ReportRead
from app.services.report_service import create_milestone_report

router = APIRouter()

@router.post("/reports/milestone", response_model=ReportRead)
def post_milestone_report(
    body: MilestoneReportRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if body.problem_count < 1 or body.problem_count > 200:
        raise HTTPException(status_code=400, detail="problem_count must be 1..200")

    report = create_milestone_report(db, current.id, body.problem_count)
    return report
