from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response

from backend.admin_metrics import get_admin_metrics
from backend.config import get_settings
from backend.services import LearningService, UserService
from backend.user_storage import UserStorageManager

settings = get_settings()
storage_manager = UserStorageManager(settings.users_dir)
user_service = UserService(storage_manager)
learning_service = LearningService(storage_manager)
admin_metrics = get_admin_metrics()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = (PROJECT_ROOT / "frontend").resolve()
ADMIN_FILE = FRONTEND_DIR / "admin.html"

TOKEN_STORAGE_KEY = "code-learning-token"
TOKEN_STORAGE_MARKER = "cookie-session"
ACCESS_TOKEN_COOKIE_NAME = "code_learning_access"
GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_OAUTH_SCOPES = "openid email profile"
OAUTH_STATE_TTL_SECONDS = 600
GOOGLE_OAUTH_REDIRECT_URI_INVALID_DETAIL = (
    "계산된 Google OAuth redirect URI가 허용 목록에 없습니다. "
    "GOOGLE_OAUTH_ALLOWED_REDIRECT_URIS와 프록시(X-Forwarded-Proto/Host) 설정을 확인하세요."
)


def request_client_id(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    return f"{host}|{user_agent[:60]}"


def require_google_oauth_settings() -> tuple[str, str]:
    client_id = settings.google_oauth_client_id
    client_secret = settings.google_oauth_client_secret
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth 설정이 누락되었습니다. .env의 GOOGLE_OAUTH_CLIENT_ID/GOOGLE_OAUTH_CLIENT_SECRET를 확인하세요.",
        )
    return client_id, client_secret


def _normalized_redirect_uri(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None

    parsed = urllib.parse.urlsplit(candidate)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.strip().lower()
    if scheme not in {"http", "https"} or not host:
        return None

    return urllib.parse.urlunsplit((scheme, host, parsed.path or "", "", ""))


def _allowed_google_oauth_redirect_uris() -> tuple[str, ...]:
    configured = tuple(
        normalized
        for normalized in (
            _normalized_redirect_uri(value) for value in settings.google_oauth_allowed_redirect_uris
        )
        if normalized
    )
    if configured:
        return configured

    legacy = _normalized_redirect_uri(settings.google_oauth_redirect_uri)
    if legacy:
        return (legacy,)

    return ()


def resolve_google_oauth_redirect_uri(request: Request, callback_route_name: str = "google_callback") -> str:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",", 1)[0].strip().lower()
    forwarded_port = (request.headers.get("x-forwarded-port") or "").split(",", 1)[0].strip()

    scheme = forwarded_proto if forwarded_proto in {"http", "https"} else (request.url.scheme or "http").lower()
    host = forwarded_host or (request.headers.get("host") or request.url.netloc or "").strip().lower()
    if forwarded_port and host and ":" not in host:
        host = f"{host}:{forwarded_port}"

    path = urllib.parse.urlsplit(str(request.url_for(callback_route_name))).path
    candidate = _normalized_redirect_uri(urllib.parse.urlunsplit((scheme, host, path, "", "")))
    allowed = _allowed_google_oauth_redirect_uris()
    if candidate and candidate in allowed:
        return candidate

    detail = GOOGLE_OAUTH_REDIRECT_URI_INVALID_DETAIL
    if candidate:
        detail = f"{detail} 계산값: {candidate}"
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _state_signature(payload: str) -> str:
    secret = (settings.google_oauth_client_secret or "").encode("utf-8")
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _normalize_next_path(next_path: str | None) -> str:
    default_path = "/dashboard.html"
    if not isinstance(next_path, str):
        return default_path

    candidate = next_path.strip()
    if not candidate:
        return default_path
    if not candidate.startswith("/"):
        return default_path
    if candidate.startswith("//"):
        return default_path
    if "\\" in candidate:
        return default_path

    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return default_path
    return candidate


def encode_state(next_path: str) -> str:
    payload = {"ts": int(time.time()), "next": _normalize_next_path(next_path)}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    signature = _state_signature(encoded)
    return f"{encoded}.{signature}"


def decode_state(state: str) -> str:
    try:
        payload, signature = state.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError("OAuth state 값이 유효하지 않습니다.") from exc

    expected = _state_signature(payload)
    if not hmac.compare_digest(expected, signature):
        raise ValueError("OAuth state 값이 유효하지 않습니다.")

    try:
        padded = payload + "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(padded).decode("utf-8")
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("OAuth state 값을 해석할 수 없습니다.") from exc

    try:
        ts = int(data.get("ts", 0))
    except (TypeError, ValueError):
        ts = 0
    if abs(time.time() - ts) > OAUTH_STATE_TTL_SECONDS:
        raise ValueError("OAuth state가 만료되었습니다. 다시 로그인해주세요.")

    return _normalize_next_path(data.get("next"))


def build_google_auth_url(
    request: Request,
    next_path: str,
    callback_route_name: str = "google_callback",
) -> str:
    client_id, _ = require_google_oauth_settings()
    redirect_uri = resolve_google_oauth_redirect_uri(request, callback_route_name)
    state = encode_state(_normalize_next_path(next_path))
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPES,
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    return f"{GOOGLE_OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    client_id, client_secret = require_google_oauth_settings()
    payload = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    request = urllib.request.Request(GOOGLE_OAUTH_TOKEN_URL, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Google 토큰 교환 요청에 실패했습니다: {exc}") from exc


def fetch_google_userinfo(access_token: str) -> dict:
    request = urllib.request.Request(GOOGLE_OAUTH_USERINFO_URL, method="GET")
    request.add_header("Authorization", f"Bearer {access_token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Google 사용자 정보 조회에 실패했습니다: {exc}") from exc


def _secure_cookie_enabled() -> bool:
    app_env = str(settings.app_env or "").strip().lower()
    return app_env not in {"dev", "development", "local", "test"}


def set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_secure_cookie_enabled(),
        samesite="lax",
        path="/",
    )


def clear_access_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=_secure_cookie_enabled(),
    )


def oauth_success_page(token: str, next_path: str) -> HTMLResponse:
    marker_js = json.dumps(TOKEN_STORAGE_MARKER)
    next_js = json.dumps(_normalize_next_path(next_path))
    key_js = json.dumps(TOKEN_STORAGE_KEY)
    content = f"""<!DOCTYPE html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>로그인 성공</title>
</head>
<body>
  <p>로그인 처리 중입니다...</p>
  <script>
    localStorage.setItem({key_js}, {marker_js});
    window.location.replace({next_js});
  </script>
</body>
</html>"""
    response = HTMLResponse(content, status_code=status.HTTP_200_OK)
    response.headers["Cache-Control"] = "no-store"
    set_access_cookie(response, token)
    return response


def oauth_error_page(message: str) -> HTMLResponse:
    safe_message = html.escape(message)
    content = f"""<!DOCTYPE html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>로그인 오류</title>
</head>
<body>
  <h1>로그인 처리에 실패했습니다.</h1>
  <p>{safe_message}</p>
  <p><a href=\"/\">홈으로 이동</a></p>
</body>
</html>"""
    return HTMLResponse(content, status_code=status.HTTP_400_BAD_REQUEST)

