from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from server.db.models import Problem, ProblemDifficulty


def list_problems(
    db: Session,
    language: str | None,
    difficulty: ProblemDifficulty | None,
    limit: int,
    offset: int,
):
    stmt = select(Problem).where(Problem.is_published == True)

    if language:
        stmt = stmt.where(Problem.language == language)
    if difficulty:
        stmt = stmt.where(Problem.difficulty == difficulty)

    # total count
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))

    # items
    items = db.scalars(
        stmt.order_by(Problem.id.desc()).limit(limit).offset(offset)
    ).all()

    return items, int(total or 0)


def get_problem(db: Session, problem_id: int) -> Problem | None:
    return db.get(Problem, problem_id)


def can_user_access_problem(problem: Problem | None, *, user_id: int) -> bool:
    if problem is None:
        return False
    if problem.is_published:
        return True
    if problem.created_by is None:
        return False
    return int(problem.created_by) == int(user_id)


def get_problem_for_user(db: Session, problem_id: int, *, user_id: int) -> Problem | None:
    problem = db.get(Problem, problem_id)
    if not can_user_access_problem(problem, user_id=user_id):
        return None
    return problem
