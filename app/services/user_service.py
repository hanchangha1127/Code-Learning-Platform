from sqlalchemy.orm import Session
from app.db.models import UserSettings, PreferredDifficulty

def get_settings(db: Session, user_id: int) -> UserSettings | None:
    return db.query(UserSettings).filter(UserSettings.user_id == user_id).first()

def update_settings(
    db: Session,
    user_id: int,
    preferred_language: str,
    preferred_difficulty: PreferredDifficulty,
) -> UserSettings:
    s = get_settings(db, user_id)
    if not s:
        s = UserSettings(user_id=user_id)
        db.add(s)

    s.preferred_language = preferred_language
    s.preferred_difficulty = preferred_difficulty

    db.commit()
    db.refresh(s)
    return s
