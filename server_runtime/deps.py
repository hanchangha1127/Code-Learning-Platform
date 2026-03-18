from __future__ import annotations

from datetime import date

from fastapi import Header, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from server_runtime.context import (
    ACCESS_TOKEN_COOKIE_NAME,
    admin_metrics,
    request_client_id,
    settings,
    user_service,
)
from server_runtime.platform_auth import resolve_username_from_access_token


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


def _resolve_username_from_jwt(token: str) -> str | None:
    try:
        jwt_username = resolve_username_from_access_token(token)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해 주세요.",
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

    cookie_token = (request.cookies.get(ACCESS_TOKEN_COOKIE_NAME) or "").strip()
    if cookie_token:
        username = _resolve_username_from_jwt(cookie_token)

    if not username:
        token, header_invalid = _extract_bearer_token(authorization)
        if header_invalid and not cookie_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer 토큰 형식이 올바르지 않습니다.",
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
                response.headers["X-Auth-Legacy-Sunset-Date"] = str(
                    getattr(settings, "legacy_token_sunset_date", "")
                )

        if not username and token:
            username = _resolve_username_from_jwt(token)

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다.",
        )

    admin_metrics.record_user_activity(username=username, client_id=request_client_id(request))
    return username
