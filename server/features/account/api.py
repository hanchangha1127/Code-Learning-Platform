from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.dependencies import get_db
from server.features.auth.dependencies import get_current_user
from server.db.models import PreferredDifficulty, User
from server.schemas.learning_continuity import LearningGoalRead, LearningGoalUpdate
from server.schemas.user import UserRead, UserSettingsRead, UserSettingsUpdate
from server.features.learning.continuity import (
    get_or_create_learning_goal,
    serialize_learning_goal,
    update_learning_goal,
)
from server.features.learning import service as learning_service
from server.features.account.service import (
    DEFAULT_PREFERRED_LANGUAGE,
    get_settings,
    get_valid_preferred_language,
    update_settings,
)

router = APIRouter()


@router.get("")
def get_me(current: User = Depends(get_current_user)):
    return learning_service.get_public_me(current)

@router.get("/settings", response_model=UserSettingsRead)
def get_me_settings(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    settings = get_settings(db, current.id)
    if settings is None:
        return update_settings(
            db,
            current.id,
            preferred_language=DEFAULT_PREFERRED_LANGUAGE,
            preferred_difficulty=PreferredDifficulty.medium,
        )

    preferred_language = get_valid_preferred_language(getattr(settings, "preferred_language", None))
    stored_language = str(getattr(settings, "preferred_language", "") or "").strip().lower()
    if preferred_language is None or preferred_language != stored_language:
        return update_settings(
            db,
            current.id,
            preferred_language=preferred_language or DEFAULT_PREFERRED_LANGUAGE,
            preferred_difficulty=getattr(settings, "preferred_difficulty", PreferredDifficulty.medium),
        )
    return settings

@router.put("/settings", response_model=UserSettingsRead)
def put_me_settings(
    body: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    try:
        return update_settings(db, current.id, body.preferred_language, body.preferred_difficulty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/goal", response_model=LearningGoalRead)
def get_me_goal(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    goal = get_or_create_learning_goal(db, current.id)
    return serialize_learning_goal(goal)


@router.put("/goal", response_model=LearningGoalRead)
def put_me_goal(
    body: LearningGoalUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    goal = update_learning_goal(
        db,
        current.id,
        daily_target_sessions=body.daily_target_sessions,
        focus_modes=body.focus_modes,
        focus_topics=body.focus_topics,
    )
    return serialize_learning_goal(goal)
