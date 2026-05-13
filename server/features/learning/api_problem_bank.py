from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from server.db.models import ProblemDifficulty, User
from server.dependencies import get_db
from server.features.auth.dependencies import get_current_user
from server.features.learning.problem_bank_service import list_problem_bank, resume_problem_bank_item
from server.schemas.problem_bank import ProblemBankListRead, ProblemBankResumeRead

router = APIRouter()


@router.get("", response_model=ProblemBankListRead)
def get_problem_bank(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    q: str | None = Query(default=None, max_length=120),
    mode: str | None = Query(default=None, max_length=50),
    language: str | None = Query(default=None, max_length=30),
    difficulty: ProblemDifficulty | None = None,
    my_status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return list_problem_bank(
        db,
        user_id=current.id,
        query=q,
        mode=mode,
        language=language,
        difficulty=difficulty.value if difficulty is not None else None,
        my_status=my_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{problem_id}/resume", response_model=ProblemBankResumeRead)
def get_problem_bank_resume(
    problem_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    try:
        return resume_problem_bank_item(db, user_id=current.id, username=current.username, problem_id=problem_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문제를 찾지 못했습니다.") from exc
