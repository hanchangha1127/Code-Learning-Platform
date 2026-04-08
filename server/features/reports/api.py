from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from server.dependencies import get_db
from server.features.auth.dependencies import get_current_user
from server.db.models import User
from server.schemas.report import LatestLearningReportRead, LearningSolutionReportRead, MilestoneReportRequest
from server.features.reports.pdf import generate_report_pdf_download, get_latest_report_download_metadata
from server.features.reports.service import create_milestone_report

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


@router.get("/reports/latest", response_model=LatestLearningReportRead)
def get_latest_report(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    return get_latest_report_download_metadata(db, current.id)


@router.get("/reports/{report_id}/pdf")
def get_report_pdf(
    report_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Response:
    try:
        filename, pdf_bytes = generate_report_pdf_download(db, current.id, report_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="리포트를 찾지 못했습니다.") from exc
    except RuntimeError as exc:
        if "report_pdf_generation_unavailable" in str(exc):
            raise HTTPException(status_code=503, detail="PDF 생성 기능을 현재 사용할 수 없습니다.") from exc
        raise HTTPException(status_code=503, detail="PDF 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )
