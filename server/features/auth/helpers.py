from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from server.core.proxy import extract_forwarded_client_ip
from server.bootstrap import (
    build_google_auth_url,
    decode_state,
    exchange_code_for_token,
    fetch_google_userinfo,
    oauth_error_page,
    oauth_success_page,
    resolve_google_oauth_redirect_uri,
    user_service,
)
from server.features.auth.platform_auth import issue_platform_access_token

_GUEST_RATE_LIMIT_PER_MINUTE = 12
_GUEST_RATE_LIMIT_WINDOW_SECONDS = 60
_guest_rate_lock = threading.Lock()
_guest_rate_attempts: dict[str, list[float]] = {}


def extract_access_token_from_request(request: Request) -> str | None:
    authorization = (request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            return token

    cookie_token = (request.cookies.get("code_learning_access") or "").strip()
    return cookie_token or None


def guest_client_id(request: Request) -> str:
    client_host = request.client.host if request.client and request.client.host else ""
    forwarded_host = extract_forwarded_client_ip(
        client_host=client_host,
        x_forwarded_for=request.headers.get("x-forwarded-for"),
        x_real_ip=request.headers.get("x-real-ip"),
    )
    return forwarded_host or client_host or "unknown"


def enforce_guest_rate_limit(
    request: Request,
    *,
    detail: str,
    per_minute: int = _GUEST_RATE_LIMIT_PER_MINUTE,
    window_seconds: int = _GUEST_RATE_LIMIT_WINDOW_SECONDS,
) -> None:
    now = time.time()
    client_id = guest_client_id(request)
    with _guest_rate_lock:
        attempts = _guest_rate_attempts.get(client_id, [])
        attempts = [ts for ts in attempts if (now - ts) <= window_seconds]
        if len(attempts) >= per_minute:
            retry_after = max(1, int(window_seconds - (now - attempts[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={"Retry-After": str(retry_after)},
            )
        attempts.append(now)
        _guest_rate_attempts[client_id] = attempts


def issue_guest_jwt() -> str:
    legacy_token = user_service.create_guest()
    username = legacy_token.partition(":")[0]
    return issue_platform_access_token(username=username, guest=True)


def start_google_login(request: Request, *, callback_route_name: str) -> Response:
    next_path = request.query_params.get("next") or "/dashboard.html"
    auth_url = build_google_auth_url(request, next_path, callback_route_name=callback_route_name)
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


def complete_google_login(
    request: Request,
    *,
    callback_route_name: str,
    code: str | None,
    state: str | None,
    error: str | None,
    oauth_error_prefix: str,
    oauth_code_missing_detail: str,
    oauth_token_missing_detail: str,
    oauth_profile_missing_detail: str,
    oauth_service_unavailable_detail: str,
) -> Response:
    if error:
        return oauth_error_page(f"{oauth_error_prefix}: {error}")
    if not code:
        return oauth_error_page(oauth_code_missing_detail)

    try:
        next_path = decode_state(state or "")
    except ValueError as exc:
        return oauth_error_page(str(exc))

    try:
        redirect_uri = resolve_google_oauth_redirect_uri(request, callback_route_name)
        token_payload = exchange_code_for_token(code, redirect_uri)
    except ValueError as exc:
        return oauth_error_page(str(exc))
    except HTTPException as exc:
        return oauth_error_page(str(exc.detail))

    access_token = token_payload.get("access_token")
    if not access_token:
        return oauth_error_page(oauth_token_missing_detail)

    try:
        profile = fetch_google_userinfo(access_token)
    except ValueError as exc:
        return oauth_error_page(str(exc))

    provider_id = str(profile.get("sub") or "")
    email = profile.get("email")
    name = profile.get("name") or profile.get("given_name")
    if not provider_id:
        return oauth_error_page(oauth_profile_missing_detail)

    try:
        username = user_service.ensure_oauth_user(
            provider="google",
            provider_id=provider_id,
            email=email,
            display_name=name,
        )
        user_info = user_service.get_user_info(username)
        token = issue_platform_access_token(
            username=username,
            email=user_info.get("email"),
            guest=bool(user_info.get("guest")),
        )
    except ValueError as exc:
        return oauth_error_page(str(exc))
    except SQLAlchemyError:
        return oauth_error_page(oauth_service_unavailable_detail)

    return oauth_success_page(token, next_path)
