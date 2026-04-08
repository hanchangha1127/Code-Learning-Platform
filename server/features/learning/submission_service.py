from sqlalchemy.orm import Session

from server.db.base import utcnow
from server.db.models import Problem, Submission, SubmissionStatus, UserProblemStat
from server.features.learning.problem_service import can_user_access_problem


def create_submission(
    db: Session,
    user_id: int,
    problem_id: int,
    language: str,
    code: str,
) -> Submission:
    # 1) Validate problem existence.
    problem = db.get(Problem, problem_id)
    if not can_user_access_problem(problem, user_id=user_id):
        raise ValueError("problem_not_found")

    # 2) Create a new submission in pending state.
    submission = Submission(
        user_id=user_id,
        problem_id=problem_id,
        language=language,
        code=code,
        status=SubmissionStatus.pending,
    )
    db.add(submission)

    # 3) Upsert user_problem_stats attempts counter.
    stat = db.get(
        UserProblemStat,
        {"user_id": user_id, "problem_id": problem_id},
    )

    now = utcnow()

    if stat is None:
        stat = UserProblemStat(
            user_id=user_id,
            problem_id=problem_id,
            attempts=1,
            last_submitted_at=now,
        )
        db.add(stat)
    else:
        stat.attempts += 1
        stat.last_submitted_at = now

    db.commit()
    db.refresh(submission)
    from server.features.learning.history import invalidate_public_history_total_for_user_id

    invalidate_public_history_total_for_user_id(db, user_id)
    return submission
