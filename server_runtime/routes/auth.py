from __future__ import annotations

import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from server_runtime.context import (
    build_google_auth_url,
    clear_access_cookie,
    decode_state,
    exchange_code_for_token,
    fetch_google_userinfo,
    oauth_error_page,
    oauth_success_page,
    resolve_google_oauth_redirect_uri,
    set_access_cookie,
    user_service,
)
from server_runtime.platform_auth import issue_platform_access_token
from server_runtime.schemas import TokenResponse

router = APIRouter()
_GUEST_RATE_LIMIT_PER_MINUTE = 12
_GUEST_RATE_LIMIT_WINDOW_SECONDS = 60
_guest_rate_lock = threading.Lock()
_guest_rate_attempts: dict[str, list[float]] = {}

GUEST_RATE_LIMIT_DETAIL = "게스트 로그인 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."
OAUTH_ERROR_PREFIX = "Google 로그인 오류"
OAUTH_CODE_MISSING_DETAIL = "로그인 코드를 받지 못해 인증을 완료할 수 없습니다."
OAUTH_TOKEN_MISSING_DETAIL = "Google 토큰 응답에 access_token이 없습니다."
OAUTH_PROFILE_MISSING_DETAIL = "Google 사용자 계정 식별자(sub)가 없어 로그인을 완료할 수 없습니다."
OAUTH_SERVICE_UNAVAILABLE_DETAIL = "로그인 서비스 연결에 실패했습니다. 잠시 후 다시 시도해 주세요."
PASSWORD_AUTH_DISABLED_DETAIL = "이메일/비밀번호 로그인은 비활성화되어 있습니다. Google 로그인만 지원합니다."
GUEST_DB_UNAVAILABLE_DETAIL = "인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해 주세요."
GUEST_POST_ONLY_DETAIL = "게스트 로그인은 POST /api/auth/guest 로만 지원합니다."



def _guest_client_id(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded_for:
        return forwarded_for
    if request.client and request.client.host:
        return request.client.host
    return "unknown"



def _enforce_guest_rate_limit(request: Request) -> None:
    now = time.time()
    client_id = _guest_client_id(request)
    with _guest_rate_lock:
        attempts = _guest_rate_attempts.get(client_id, [])
        attempts = [ts for ts in attempts if (now - ts) <= _GUEST_RATE_LIMIT_WINDOW_SECONDS]
        if len(attempts) >= _GUEST_RATE_LIMIT_PER_MINUTE:
            retry_after = max(1, int(_GUEST_RATE_LIMIT_WINDOW_SECONDS - (now - attempts[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=GUEST_RATE_LIMIT_DETAIL,
                headers={"Retry-After": str(retry_after)},
            )
        attempts.append(now)
        _guest_rate_attempts[client_id] = attempts



def _issue_guest_jwt() -> str:
    legacy_token = user_service.create_guest()
    username = legacy_token.partition(":")[0]
    return issue_platform_access_token(username=username, guest=True)


@router.get("/api/auth/google/start")
def google_login_start(request: Request) -> Response:
    next_path = request.query_params.get("next") or "/dashboard.html"
    auth_url = build_google_auth_url(request, next_path, callback_route_name="google_callback")
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/api/auth/google/callback", name="google_callback")
def google_login_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    if error:
        return oauth_error_page(f"{OAUTH_ERROR_PREFIX}: {error}")
    if not code:
        return oauth_error_page(OAUTH_CODE_MISSING_DETAIL)

    try:
        next_path = decode_state(state or "")
    except ValueError as exc:
        return oauth_error_page(str(exc))

    try:
        redirect_uri = resolve_google_oauth_redirect_uri(request, "google_callback")
        token_payload = exchange_code_for_token(code, redirect_uri)
    except ValueError as exc:
        return oauth_error_page(str(exc))
    except HTTPException as exc:
        return oauth_error_page(str(exc.detail))

    access_token = token_payload.get("access_token")
    if not access_token:
        return oauth_error_page(OAUTH_TOKEN_MISSING_DETAIL)

    try:
        profile = fetch_google_userinfo(access_token)
    except ValueError as exc:
        return oauth_error_page(str(exc))

    provider_id = str(profile.get("sub") or "")
    email = profile.get("email")
    name = profile.get("name") or profile.get("given_name")
    if not provider_id:
        return oauth_error_page(OAUTH_PROFILE_MISSING_DETAIL)

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
        return oauth_error_page(OAUTH_SERVICE_UNAVAILABLE_DETAIL)

    return oauth_success_page(token, next_path)


@router.post("/api/auth/register")
def register_disabled() -> None:
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=PASSWORD_AUTH_DISABLED_DETAIL)


@router.post("/api/auth/login")
def login_disabled() -> None:
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=PASSWORD_AUTH_DISABLED_DETAIL)


@router.post("/api/auth/guest", response_model=TokenResponse)
def guest_login(request: Request, response: Response) -> TokenResponse:
    _enforce_guest_rate_limit(request)
    try:
        token = _issue_guest_jwt()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=GUEST_DB_UNAVAILABLE_DETAIL) from exc
    set_access_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(token=token)


@router.get("/api/auth/guest/start")
def guest_login_start() -> Response:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=GUEST_POST_ONLY_DETAIL,
        headers={"Allow": "POST"},
    )


@router.post("/api/auth/logout")
def logout(response: Response) -> dict:
    clear_access_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
