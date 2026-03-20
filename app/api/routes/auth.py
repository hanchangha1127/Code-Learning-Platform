from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, SignUpRequest, TokenResponse
from app.services.auth_service import login, logout, refresh_tokens, signup
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
from server_runtime.routes import auth as runtime_auth_routes

router = APIRouter()

PASSWORD_AUTH_DISABLED_DETAIL = "이메일/비밀번호 로그인은 기본적으로 비활성화되어 있습니다."
OAUTH_ERROR_PREFIX = "Google 로그인 오류"
OAUTH_CODE_MISSING_DETAIL = "로그인 코드를 받지 못했습니다."
OAUTH_TOKEN_MISSING_DETAIL = "Google 토큰 응답에 access_token이 없습니다."
OAUTH_PROFILE_MISSING_DETAIL = "Google 사용자 계정 식별자(sub)가 없습니다."
OAUTH_SERVICE_UNAVAILABLE_DETAIL = "로그인 서비스 연결에 실패했습니다. 잠시 후 다시 시도해 주세요."
GUEST_DB_UNAVAILABLE_DETAIL = "인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해 주세요."


def _access_token_from_request(request: Request) -> str | None:
    authorization = (request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            return token

    cookie_token = (request.cookies.get("code_learning_access") or "").strip()
    return cookie_token or None


def _require_password_auth_enabled() -> None:
    if settings.ALLOW_PLATFORM_PASSWORD_AUTH:
        return
    raise HTTPException(status_code=410, detail=PASSWORD_AUTH_DISABLED_DETAIL)


@router.get("/google/start")
def get_google_start(request: Request) -> Response:
    next_path = request.query_params.get("next") or "/dashboard.html"
    auth_url = build_google_auth_url(request, next_path, callback_route_name="platform_google_callback")
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/google/callback", name="platform_google_callback")
def get_google_callback(
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
        redirect_uri = resolve_google_oauth_redirect_uri(request, "platform_google_callback")
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


@router.post("/guest")
def post_guest(request: Request, response: Response) -> dict:
    runtime_auth_routes._enforce_guest_rate_limit(request)
    try:
        token = runtime_auth_routes._issue_guest_jwt()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=GUEST_DB_UNAVAILABLE_DETAIL) from exc

    set_access_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"
    return {"token": token}


@router.post("/signup")
def post_signup(body: SignUpRequest, db: Session = Depends(get_db)):
    _require_password_auth_enabled()
    try:
        user = signup(db, body.email, body.username, body.password)
        return {"id": user.id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse)
def post_login(body: LoginRequest, db: Session = Depends(get_db)):
    _require_password_auth_enabled()
    try:
        access, refresh = login(db, body.username, body.password)
        return TokenResponse(access_token=access, refresh_token=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/refresh", response_model=TokenResponse)
def post_refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    _require_password_auth_enabled()
    try:
        access, refresh = refresh_tokens(db, body.refresh_token)
        return TokenResponse(access_token=access, refresh_token=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout")
def post_logout(
    request: Request,
    response: Response,
    body: LogoutRequest | None = None,
    db: Session = Depends(get_db),
):
    logout(
        db,
        body.refresh_token if body is not None else None,
        access_token=_access_token_from_request(request),
    )
    clear_access_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
