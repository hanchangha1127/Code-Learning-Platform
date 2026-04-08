from __future__ import annotations

from datetime import date

from fastapi import Header, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from server.core.security import is_sidless_cookie_compat_active
from server.bootstrap import (
    ACCESS_TOKEN_COOKIE_NAME,
    admin_metrics,
    request_client_id,
    set_access_cookie,
    settings,
    user_service,
)
from server.features.auth.platform_auth import resolve_username_from_access_token, upgrade_legacy_access_cookie
from server.db.session import SessionLocal


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

INVALID_BEARER_DETAIL = "Bearer 토큰 형식이 올바르지 않습니다."
INVALID_TOKEN_DETAIL = "유효하지 않거나 만료된 토큰입니다."
AUTH_DB_UNAVAILABLE_DETAIL = "인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해 주세요."


def _extract_bearer_token(authorization: str | None) -> tuple[str | None, bool]:
    header_value = (authorization or "").strip()
    if not header_value:
        return None, False
    if not header_value.lower().startswith("bearer "):
        return None, True

    token = header_value.split(" ", 1)[1].strip()
    if not token:
        return None, True
    return token, False


def _legacy_auth_allowed_now() -> bool:
    raw = str(getattr(settings, "legacy_token_sunset_date", "") or "").strip()
    if not raw:
        return True
    try:
        sunset = date.fromisoformat(raw)
    except ValueError:
        return False
    return date.today() <= sunset


def _sidless_cookie_compat_allowed_now() -> bool:
    return is_sidless_cookie_compat_active(
        bool(getattr(settings, "allow_sidless_cookie_compat", False)),
        str(getattr(settings, "sidless_cookie_sunset_at", "") or ""),
    )


def _resolve_username_from_jwt(token: str) -> str | None:
    try:
        jwt_username = resolve_username_from_access_token(token)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=AUTH_DB_UNAVAILABLE_DETAIL,
        ) from exc

    if not jwt_username:
        return None

    try:
        return user_service.ensure_local_user(jwt_username)
    except ValueError:
        return None


def get_current_username(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    username = None
    token, header_invalid = _extract_bearer_token(authorization)
    if header_invalid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_BEARER_DETAIL,
        )

    if token and settings.allow_legacy_jsonl_tokens and _legacy_auth_allowed_now():
        try:
            max_age = max(int(getattr(settings, "legacy_token_max_age_seconds", 86400) or 0), 0)
        except (TypeError, ValueError):
            max_age = 0
        if max_age > 0:
            username = user_service.get_user_by_token(token, max_age_seconds=max_age)
        if username:
            response.headers["X-Auth-Legacy-Token"] = "true"
            response.headers["X-Auth-Legacy-Sunset-At"] = str(
                getattr(settings, "legacy_token_sunset_date", "")
            )

    if token and not username:
        username = _resolve_username_from_jwt(token)

    if token and not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_TOKEN_DETAIL,
        )

    if not username:
        cookie_token = (request.cookies.get(ACCESS_TOKEN_COOKIE_NAME) or "").strip()
        if cookie_token:
            username = _resolve_username_from_jwt(cookie_token)
            if not username and _sidless_cookie_compat_allowed_now():
                upgraded = upgrade_legacy_access_cookie(cookie_token)
                if upgraded is not None:
                    username, replacement_token = upgraded
                    set_access_cookie(response, replacement_token)
                    response.headers["X-Auth-Legacy-Token"] = "true"
                    response.headers["X-Auth-Legacy-Sunset-At"] = str(
                        getattr(settings, "sidless_cookie_sunset_at", "")
                    )

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_TOKEN_DETAIL,
        )

    admin_metrics.record_user_activity(username=username, client_id=request_client_id(request))
    return username
