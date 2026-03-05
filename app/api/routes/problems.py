from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.db.models import ProblemDifficulty, User
from app.schemas.problem import ProblemListResponse, ProblemRead
from app.services.problem_service import get_problem_for_user, list_problems

router = APIRouter()


@router.get("", response_model=ProblemListResponse)
def get_problems(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    language: str | None = None,
    difficulty: ProblemDifficulty | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # Use user preferences as defaults when explicit query params are missing.
    if not language and current.settings:
        language = current.settings.preferred_language

    if not difficulty and current.settings and current.settings.preferred_difficulty is not None:
        preferred = current.settings.preferred_difficulty
        preferred_value = preferred.value if hasattr(preferred, "value") else str(preferred)
        try:
            difficulty = ProblemDifficulty(preferred_value)
        except ValueError:
            difficulty = None

    items, total = list_problems(db, language, difficulty, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{problem_id}", response_model=ProblemRead)
def get_problem_detail(
    problem_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    problem = get_problem_for_user(db, problem_id, user_id=current.id)
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem
