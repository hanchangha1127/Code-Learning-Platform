# app/services/auth_service.py
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_expires_at,
    verify_password,
)
from app.db.base import utcnow
from app.db.models import PreferredDifficulty, User, UserSession, UserSettings, UserStatus


def signup(db: Session, email: str, username: str, password: str) -> User:
    if db.query(User).filter(User.email == email).first():
        raise ValueError("email already exists")
    if db.query(User).filter(User.username == username).first():
        raise ValueError("username already exists")

    user = User(email=email, username=username, password_hash=hash_password(password))
    db.add(user)
    db.flush()

    db.add(
        UserSettings(
            user_id=user.id,
            preferred_language="python",
            preferred_difficulty=PreferredDifficulty.medium,
        )
    )

    db.commit()
    db.refresh(user)
    return user


def login(db: Session, username: str, password: str) -> tuple[str, str]:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("invalid credentials")

    if user.status != UserStatus.active:
        raise ValueError("account is not active")

    access = create_access_token(user.id)
    refresh = create_refresh_token()

    db.add(
        UserSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh),
            expires_at=refresh_expires_at(),
            revoked_at=None,
        )
    )
    db.commit()

    return access, refresh


def refresh_tokens(db: Session, refresh_token: str) -> tuple[str, str]:
    token_hash = hash_refresh_token(refresh_token)
    now = utcnow()

    session = (
        db.query(UserSession)
        .join(User, User.id == UserSession.user_id)
        .filter(
            and_(
                UserSession.refresh_token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                User.status == UserStatus.active,
            )
        )
        .first()
    )

    if not session:
        raise ValueError("invalid refresh token")

    # Rotate refresh token: revoke current token and issue a new pair.
    session.revoked_at = now
    user_id = session.user_id

    new_access = create_access_token(user_id)
    new_refresh = create_refresh_token()

    db.add(
        UserSession(
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(new_refresh),
            expires_at=refresh_expires_at(),
            revoked_at=None,
        )
    )
    db.commit()

    return new_access, new_refresh


def logout(db: Session, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    now = utcnow()

    session = (
        db.query(UserSession)
        .filter(
            and_(
                UserSession.refresh_token_hash == token_hash,
                UserSession.revoked_at.is_(None),
            )
        )
        .first()
    )

    if not session:
        # Already logged out / expired token is treated as idempotent success.
        return

    session.revoked_at = now
    db.commit()
