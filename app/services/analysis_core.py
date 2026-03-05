from sqlalchemy.orm import Session

from app.db.models import AIAnalysis, AnalysisType, Submission, SubmissionStatus
from app.services.ai_providers import get_provider
from app.services.problem_stat_service import update_user_problem_stat


def analyze_submission(db: Session, submission_id: int, user_id: int):
    sub = db.get(Submission, submission_id)
    if not sub or sub.user_id != user_id:
        raise ValueError("submission_not_found")

    provider = get_provider()

    code = sub.code
    language = getattr(sub, "language", "python")

    if sub.problem is not None and sub.problem.description:
        problem_prompt = sub.problem.description
    elif sub.problem is not None and sub.problem.title:
        problem_prompt = sub.problem.title
    else:
        problem_prompt = f"Problem #{sub.problem_id}"

    result = provider.analyze(
        language=language,
        code=code,
        problem_prompt=problem_prompt,
    )

    sub.score = int(result.score)
    sub.status = SubmissionStatus.passed if result.status == "passed" else SubmissionStatus.failed

    db.add(
        AIAnalysis(
            user_id=user_id,
            submission_id=submission_id,
            analysis_type=AnalysisType.review,
            result_summary=result.summary,
            result_detail=str(result.detail),
        )
    )

    update_user_problem_stat(
        db=db,
        user_id=user_id,
        problem_id=sub.problem_id,
        score=sub.score,
        status=sub.status,
        analysis_summary=result.summary,
        analysis_detail=result.detail,
    )
