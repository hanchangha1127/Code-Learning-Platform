from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from server.db.session import SessionLocal
from server.features.auth.service import logout as revoke_platform_session
from server.features.auth import helpers as auth_helpers
from server.bootstrap import clear_access_cookie, set_access_cookie
from server.schemas.runtime import TokenResponse

router = APIRouter()

GUEST_RATE_LIMIT_DETAIL = "게스트 로그인 요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
OAUTH_ERROR_PREFIX = "Google 로그인 오류"
OAUTH_CODE_MISSING_DETAIL = "로그인 코드를 받지 못해 인증을 완료할 수 없습니다."
OAUTH_TOKEN_MISSING_DETAIL = "Google 토큰 응답에 access_token이 없습니다."
OAUTH_PROFILE_MISSING_DETAIL = "Google 사용자 계정 식별자(sub)가 없어 로그인을 완료할 수 없습니다."
OAUTH_SERVICE_UNAVAILABLE_DETAIL = "로그인 서비스 연결에 실패했습니다. 잠시 후 다시 시도해주세요."
PASSWORD_AUTH_DISABLED_DETAIL = "이메일/비밀번호 로그인은 비활성화되어 있습니다. Google 로그인만 지원합니다."
GUEST_DB_UNAVAILABLE_DETAIL = "인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해 주세요."
GUEST_POST_ONLY_DETAIL = "게스트 로그인은 POST /api/auth/guest 로만 지원합니다."


def _guest_client_id(request: Request) -> str:
    return auth_helpers.guest_client_id(request)


def _enforce_guest_rate_limit(request: Request) -> None:
    auth_helpers.enforce_guest_rate_limit(request, detail=GUEST_RATE_LIMIT_DETAIL)


def _issue_guest_jwt() -> str:
    return auth_helpers.issue_guest_jwt()


def _access_token_from_request(request: Request) -> str | None:
    return auth_helpers.extract_access_token_from_request(request)


@router.get("/api/auth/google/start")
def google_login_start(request: Request) -> Response:
    return auth_helpers.start_google_login(request, callback_route_name="google_callback")


@router.get("/api/auth/google/callback", name="google_callback")
def google_login_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    return auth_helpers.complete_google_login(
        request,
        callback_route_name="google_callback",
        code=code,
        state=state,
        error=error,
        oauth_error_prefix=OAUTH_ERROR_PREFIX,
        oauth_code_missing_detail=OAUTH_CODE_MISSING_DETAIL,
        oauth_token_missing_detail=OAUTH_TOKEN_MISSING_DETAIL,
        oauth_profile_missing_detail=OAUTH_PROFILE_MISSING_DETAIL,
        oauth_service_unavailable_detail=OAUTH_SERVICE_UNAVAILABLE_DETAIL,
    )


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
def logout(request: Request, response: Response) -> dict:
    access_token = _access_token_from_request(request)
    if access_token:
        with SessionLocal() as db:
            revoke_platform_session(db, access_token=access_token)
    clear_access_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
