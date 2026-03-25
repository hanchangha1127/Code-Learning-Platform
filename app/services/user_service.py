from sqlalchemy.orm import Session

from app.db.models import UserSettings, PreferredDifficulty
from backend.content import LANGUAGES, LANGUAGE_ALIASES, normalize_language_id

DEFAULT_PREFERRED_LANGUAGE = "python"
SUPPORTED_PREFERRED_LANGUAGES = frozenset({*LANGUAGES.keys(), *LANGUAGE_ALIASES.keys()})


def get_valid_preferred_language(preferred_language: str | None) -> str | None:
    normalized = normalize_language_id(preferred_language)
    if normalized in LANGUAGES:
        return normalized
    return None


def normalize_preferred_language(
    preferred_language: str | None,
    *,
    fallback_to_default: bool = False,
) -> str:
    normalized = get_valid_preferred_language(preferred_language)
    if normalized is not None:
        return normalized
    if fallback_to_default:
        return DEFAULT_PREFERRED_LANGUAGE
    raise ValueError("지원하지 않는 언어입니다.")

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

    s.preferred_language = normalize_preferred_language(preferred_language)
    s.preferred_difficulty = preferred_difficulty

    db.commit()
    db.refresh(s)
    return s
