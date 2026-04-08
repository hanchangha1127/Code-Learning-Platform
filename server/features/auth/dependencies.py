import logging

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from server.dependencies import get_db
from server.core.config import settings
from server.core.security import is_sidless_cookie_compat_active, parse_access_token
from server.db.base import utcnow
from server.db.models import User, UserSession, UserStatus
from server.features.auth.service import issue_non_refreshable_access_token
from server.bootstrap import set_access_cookie
from server.infra.admin_metrics import get_admin_metrics

ACCESS_TOKEN_COOKIE_NAME = "code_learning_access"
bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
_admin_metrics = get_admin_metrics()
_LEGACY_COOKIE_HEADER_NAME = "X-Auth-Legacy-Token"
_LEGACY_COOKIE_SUNSET_HEADER_NAME = "X-Auth-Legacy-Sunset-At"


def _request_client_id(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    return f"{host}|{user_agent[:60]}"


def _record_user_activity_best_effort(request: Request, user: User) -> None:
    username = str(getattr(user, "username", "") or "").strip()
    if not username:
        return

    try:
        _admin_metrics.record_user_activity(
            username=username,
            client_id=_request_client_id(request),
        )
    except Exception:
        logger.debug("failed_to_record_platform_user_activity", exc_info=True)


def get_current_user(
    request: Request,
    response: Response,
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    def _require_active_session(user_id: int, session_id: int) -> None:
        active_session = (
            db.query(UserSession)
            .filter(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utcnow(),
            )
            .first()
        )
        if active_session is None:
            raise ValueError("session revoked")

    def _resolve_user_id(token: str) -> int:
        _, user_id, session_id = parse_access_token(token, require_session=True)
        _require_active_session(user_id, session_id)
        return user_id

    def _set_legacy_cookie_headers() -> None:
        response.headers[_LEGACY_COOKIE_HEADER_NAME] = "true"
        response.headers[_LEGACY_COOKIE_SUNSET_HEADER_NAME] = settings.SIDLESS_COOKIE_SUNSET_AT

    def _resolve_legacy_cookie_user(token: str) -> User | None:
        if not is_sidless_cookie_compat_active(
            settings.ALLOW_SIDLESS_COOKIE_COMPAT,
            settings.SIDLESS_COOKIE_SUNSET_AT,
        ):
            return None
        try:
            _, legacy_user_id, session_id = parse_access_token(token, require_session=False)
        except Exception:
            return None
        if session_id is not None:
            return None

        user = db.query(User).filter(User.id == legacy_user_id).first()
        if not user or user.status != UserStatus.active:
            return None

        replacement_token = issue_non_refreshable_access_token(db, user.id)
        db.commit()
        set_access_cookie(response, replacement_token)
        _set_legacy_cookie_headers()
        return user

    user_id: int | None = None
    resolved_user: User | None = None
    bearer_token = str(getattr(cred, "credentials", "") or "").strip() if cred is not None else ""
    if bearer_token:
        try:
            user_id = _resolve_user_id(bearer_token)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    cookie_token = (request.cookies.get(ACCESS_TOKEN_COOKIE_NAME) or "").strip()
    if user_id is None and cookie_token:
        try:
            user_id = _resolve_user_id(cookie_token)
        except Exception:
            resolved_user = _resolve_legacy_cookie_user(cookie_token)
            user_id = resolved_user.id if resolved_user is not None else None

    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = resolved_user or db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if user.status != UserStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active")

    _record_user_activity_best_effort(request, user)
    return user
