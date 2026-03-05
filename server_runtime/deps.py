from __future__ import annotations

from fastapi import Header, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from server_runtime.context import admin_metrics, request_client_id, settings, user_service
from server_runtime.platform_auth import resolve_username_from_access_token


def get_current_username(
    request: Request,
    response: Response,
    authorization: str = Header(..., alias="Authorization"),
) -> str:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer 토큰 형식이 올바르지 않습니다.",
        )

    token = authorization.split(" ", 1)[1].strip()

    username = None

    # Backward compatibility window for legacy JSONL session tokens.
    if settings.allow_legacy_jsonl_tokens:
        username = user_service.get_user_by_token(token)
        if username:
            response.headers["X-Auth-Legacy-Token"] = "true"
            response.headers["X-Auth-Legacy-Sunset-Date"] = settings.legacy_token_sunset_date

    # Unified auth path: accept platform JWT and bootstrap local JSONL profile lazily.
    if not username:
        try:
            jwt_username = resolve_username_from_access_token(token)
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해주세요.",
            ) from exc

        if jwt_username:
            try:
                username = user_service.ensure_local_user(jwt_username)
            except ValueError:
                username = None

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다.",
        )

    admin_metrics.record_user_activity(username=username, client_id=request_client_id(request))
    return username
