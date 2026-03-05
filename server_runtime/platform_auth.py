from __future__ import annotations

import secrets
from typing import Iterable

from app.core.security import create_access_token, decode_access_token, hash_password
from app.db.models import PreferredDifficulty, User, UserSettings, UserStatus
from app.db.session import SessionLocal


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


def _pick_available_email(username: str, explicit_email: str | None, *, guest: bool) -> str:
    with SessionLocal() as db:
        for candidate in _email_candidates(username, explicit_email, guest=guest):
            exists = db.query(User).filter(User.email == candidate).first()
            if not exists:
                return candidate
    raise ValueError("사용 가능한 이메일 식별자를 생성할 수 없습니다.")


def ensure_platform_user(
    *,
    username: str,
    email: str | None = None,
    guest: bool = False,
) -> User:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()

        if user is None:
            resolved_email = _pick_available_email(username, email, guest=guest)
            random_password = secrets.token_urlsafe(24)
            user = User(
                email=resolved_email,
                username=username,
                password_hash=hash_password(random_password),
            )
            db.add(user)
            db.flush()

            db.add(
                UserSettings(
                    user_id=user.id,
                    preferred_language="python",
                    preferred_difficulty=PreferredDifficulty.medium,
                )
            )
        else:
            settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
            if settings is None:
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


def issue_platform_access_token(
    *,
    username: str,
    email: str | None = None,
    guest: bool = False,
) -> str:
    user = ensure_platform_user(username=username, email=email, guest=guest)
    if user.status != UserStatus.active:
        raise ValueError("account is not active")
    return create_access_token(user.id)


def resolve_username_from_access_token(token: str) -> str | None:
    try:
        payload = decode_access_token(token)
        if payload.get("type") != "access":
            return None
        user_id = int(payload["sub"])
    except Exception:
        return None

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.status != UserStatus.active:
            return None
        return user.username
