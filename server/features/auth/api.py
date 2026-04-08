from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from server.dependencies import get_db
from server.core.config import settings
from server.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, SignUpRequest, TokenResponse
from server.features.auth.service import login, logout, refresh_tokens, signup
from server.features.auth import helpers as auth_helpers
from server.bootstrap import clear_access_cookie, set_access_cookie
from server.features.auth import legacy_api as runtime_auth_routes

router = APIRouter()

PASSWORD_AUTH_DISABLED_DETAIL = "이메일/비밀번호 로그인은 기본적으로 비활성화되어 있습니다."
OAUTH_ERROR_PREFIX = "Google 로그인 오류"
OAUTH_CODE_MISSING_DETAIL = "로그인 코드를 받지 못해 인증을 완료할 수 없습니다."
OAUTH_TOKEN_MISSING_DETAIL = "Google 토큰 응답에 access_token이 없습니다."
OAUTH_PROFILE_MISSING_DETAIL = "Google 사용자 계정 식별자(sub)가 없어 로그인을 완료할 수 없습니다."
OAUTH_SERVICE_UNAVAILABLE_DETAIL = "로그인 서비스 연결에 실패했습니다. 잠시 후 다시 시도해주세요."
GUEST_DB_UNAVAILABLE_DETAIL = "인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해 주세요."


def _require_password_auth_enabled() -> None:
    if settings.ALLOW_PLATFORM_PASSWORD_AUTH:
        return
    raise HTTPException(status_code=410, detail=PASSWORD_AUTH_DISABLED_DETAIL)


@router.get("/google/start")
def get_google_start(request: Request) -> Response:
    return auth_helpers.start_google_login(request, callback_route_name="platform_google_callback")


@router.get("/google/callback", name="platform_google_callback")
def get_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    return auth_helpers.complete_google_login(
        request,
        callback_route_name="platform_google_callback",
        code=code,
        state=state,
        error=error,
        oauth_error_prefix=OAUTH_ERROR_PREFIX,
        oauth_code_missing_detail=OAUTH_CODE_MISSING_DETAIL,
        oauth_token_missing_detail=OAUTH_TOKEN_MISSING_DETAIL,
        oauth_profile_missing_detail=OAUTH_PROFILE_MISSING_DETAIL,
        oauth_service_unavailable_detail=OAUTH_SERVICE_UNAVAILABLE_DETAIL,
    )


@router.post("/guest")
def post_guest(request: Request, response: Response) -> dict:
    runtime_auth_routes._enforce_guest_rate_limit(request)
    try:
        token = runtime_auth_routes._issue_guest_jwt()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=GUEST_DB_UNAVAILABLE_DETAIL) from exc

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
        access_token=auth_helpers.extract_access_token_from_request(request),
    )
    clear_access_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
