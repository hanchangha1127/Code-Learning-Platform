from __future__ import annotations

import secrets
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password,
    parse_access_token,
)
from app.db.base import utcnow
from app.db.models import PreferredDifficulty, User, UserSession, UserSettings, UserStatus
from app.db.session import SessionLocal
from app.services.auth_service import issue_non_refreshable_access_token

_PLATFORM_USER_CREATE_RETRIES = 5


def _email_candidates(username: str, explicit_email: str | None, *, guest: bool) -> Iterable[str]:
    if explicit_email:
        normalized = explicit_email.strip().lower()
        if normalized:
            yield normalized

    domain = "guest.local" if guest else "jsonl.local"
    base = f"{username}@{domain}".lower()
    yield base
    for _ in range(8):
        suffix = secrets.token_hex(3)
        yield f"{username}.{suffix}@{domain}".lower()


def _pick_available_email(db: Session, username: str, explicit_email: str | None, *, guest: bool) -> str:
    for candidate in _email_candidates(username, explicit_email, guest=guest):
        exists = db.query(User).filter(User.email == candidate).first()
        if not exists:
            return candidate
    raise ValueError("사용 가능한 이메일 식별자를 생성할 수 없습니다.")


def _ensure_default_settings(db: Session, user_id: int) -> None:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings is None:
        db.add(
            UserSettings(
                user_id=user_id,
                preferred_language="python",
                preferred_difficulty=PreferredDifficulty.medium,
            )
        )


def _issue_session_bound_access_token(db: Session, user_id: int) -> str:
    return issue_non_refreshable_access_token(db, user_id)


def ensure_platform_user(
    *,
    username: str,
    email: str | None = None,
    guest: bool = False,
) -> User:
    last_integrity_error: IntegrityError | None = None
    with SessionLocal() as db:
        for _ in range(_PLATFORM_USER_CREATE_RETRIES):
            user = db.query(User).filter(User.username == username).first()

            if user is None:
                resolved_email = _pick_available_email(db, username, email, guest=guest)
                random_password = secrets.token_urlsafe(24)
                user = User(
                    email=resolved_email,
                    username=username,
                    password_hash=hash_password(random_password),
                )
                db.add(user)
                try:
                    db.flush()
                except IntegrityError as exc:
                    db.rollback()
                    last_integrity_error = exc
                    continue

            _ensure_default_settings(db, user.id)
            try:
                db.flush()
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                last_integrity_error = exc
                continue

            refreshed_user = db.query(User).filter(User.username == username).first()
            if refreshed_user is not None:
                return refreshed_user
            raise RuntimeError("platform_user_creation_inconsistent")

    if last_integrity_error is not None:
        raise RuntimeError("platform_user_creation_failed_after_retries") from last_integrity_error
    raise RuntimeError("platform_user_creation_failed_after_retries")


def issue_platform_access_token(
    *,
    username: str,
    email: str | None = None,
    guest: bool = False,
) -> str:
    user = ensure_platform_user(username=username, email=email, guest=guest)
    if user.status != UserStatus.active:
        raise ValueError("account is not active")
    with SessionLocal() as db:
        token = _issue_session_bound_access_token(db, user.id)
        db.commit()
    return token


def resolve_username_from_access_token(token: str) -> str | None:
    try:
        _, user_id, session_id = parse_access_token(token, require_session=True)
    except Exception:
        return None

    with SessionLocal() as db:
        session = (
            db.query(UserSession)
            .filter(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utcnow(),
            )
            .first()
        )
        if session is None:
            return None
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.status != UserStatus.active:
            return None
        return user.username


def upgrade_legacy_access_cookie(token: str) -> tuple[str, str] | None:
    try:
        _, user_id, session_id = parse_access_token(token, require_session=False)
    except Exception:
        return None
    if session_id is not None:
        return None

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.status != UserStatus.active:
            return None
        new_token = issue_non_refreshable_access_token(db, user.id)
        db.commit()
        return user.username, new_token
