from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.db.models import PreferredDifficulty, User
from app.schemas.user import UserRead, UserSettingsRead, UserSettingsUpdate
from app.services.user_service import get_settings, update_settings

router = APIRouter()

@router.get("", response_model=UserRead)
def get_me(current: User = Depends(get_current_user)):
    return current

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
            preferred_language="python",
            preferred_difficulty=PreferredDifficulty.medium,
        )
    return settings

@router.put("/settings", response_model=UserSettingsRead)
def put_me_settings(
    body: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return update_settings(db, current.id, body.preferred_language, body.preferred_difficulty)
