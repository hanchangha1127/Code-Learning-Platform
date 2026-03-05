from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from server_runtime.context import (
    build_google_auth_url,
    decode_state,
    exchange_code_for_token,
    fetch_google_userinfo,
    oauth_error_page,
    oauth_success_page,
    settings,
    user_service,
)
from server_runtime.platform_auth import issue_platform_access_token
from server_runtime.schemas import TokenResponse

router = APIRouter()


def _issue_guest_jwt() -> str:
    legacy_token = user_service.create_guest()
    username = legacy_token.partition(":")[0]
    return issue_platform_access_token(username=username, guest=True)


@router.get("/api/auth/google/start")
def google_login_start(request: Request) -> Response:
    next_path = request.query_params.get("next") or "/dashboard.html"
    auth_url = build_google_auth_url(request, next_path)
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/api/auth/google/callback", name="google_callback")
def google_login_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    if error:
        return oauth_error_page(f"Google 로그인 오류: {error}")
    if not code:
        return oauth_error_page("로그인 코드가 없어 인증을 완료할 수 없습니다.")

    try:
        next_path = decode_state(state or "")
    except ValueError as exc:
        return oauth_error_page(str(exc))

    redirect_uri = settings.google_oauth_redirect_uri or str(request.url_for("google_callback"))
    try:
        token_payload = exchange_code_for_token(code, redirect_uri)
    except ValueError as exc:
        return oauth_error_page(str(exc))

    access_token = token_payload.get("access_token")
    if not access_token:
        return oauth_error_page("Google 토큰 응답에 access_token이 없습니다.")

    try:
        profile = fetch_google_userinfo(access_token)
    except ValueError as exc:
        return oauth_error_page(str(exc))

    provider_id = str(profile.get("sub") or "")
    email = profile.get("email")
    name = profile.get("name") or profile.get("given_name")
    if not provider_id:
        return oauth_error_page("Google 사용자 식별자(sub)가 없어 로그인할 수 없습니다.")

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
        return oauth_error_page("로그인 서비스가 준비되지 않았습니다. 잠시 후 다시 시도해주세요.")

    return oauth_success_page(token, next_path)


@router.post("/api/auth/register")
def register_disabled() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="아이디/비밀번호 회원가입은 비활성화되었습니다. Google 로그인만 지원합니다.",
    )


@router.post("/api/auth/login")
def login_disabled() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="아이디/비밀번호 로그인은 비활성화되었습니다. Google 로그인만 지원합니다.",
    )


@router.post("/api/auth/guest", response_model=TokenResponse)
def guest_login() -> TokenResponse:
    try:
        token = _issue_guest_jwt()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해주세요.",
        ) from exc
    return TokenResponse(token=token)


@router.get("/api/auth/guest/start")
def guest_login_start(request: Request) -> Response:
    try:
        token = _issue_guest_jwt()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="인증 서비스(DB) 연결에 실패했습니다. MySQL 상태를 확인해주세요.",
        ) from exc
    next_path = request.query_params.get("next") or "/dashboard.html"
    return oauth_success_page(token, next_path)
