# app/core/security.py
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def create_access_token(user_id: int, *, session_id: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRES_MIN)).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    if session_id is not None:
        payload["sid"] = str(session_id)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def parse_access_token(token: str, *, require_session: bool = False) -> tuple[dict[str, Any], int, int | None]:
    payload = decode_access_token(token)
    if payload.get("type") != "access":
        raise ValueError("invalid token type")

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid subject") from exc

    raw_session_id = payload.get("sid")
    if raw_session_id in (None, ""):
        if require_session:
            raise ValueError("session required")
        return payload, user_id, None

    try:
        session_id = int(raw_session_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid session id") from exc

    return payload, user_id, session_id


def access_expires_at() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRES_MIN)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])


def parse_compat_sunset_at(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def is_sidless_cookie_compat_active(
    enabled: bool,
    sunset_at: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    if not enabled:
        return False
    deadline = parse_compat_sunset_at(sunset_at)
    if deadline is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc) <= deadline


# -------- Refresh token helpers --------
def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_expires_at() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=settings.REFRESH_TOKEN_EXPIRES_DAYS)


def non_refresh_session_expires_at() -> datetime:
    return access_expires_at()
