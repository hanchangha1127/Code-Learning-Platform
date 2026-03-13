from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import decode_access_token
from app.db.models import User, UserStatus

ACCESS_TOKEN_COOKIE_NAME = "code_learning_access"
bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    def _resolve_user_id(token: str) -> int:
        payload = decode_access_token(token)
        if payload.get("type") != "access":
            raise ValueError("invalid token type")
        return int(payload["sub"])

    user_id: int | None = None
    cookie_token = (request.cookies.get(ACCESS_TOKEN_COOKIE_NAME) or "").strip()
    if cookie_token:
        try:
            user_id = _resolve_user_id(cookie_token)
        except Exception:
            user_id = None

    if user_id is None and cred is not None:
        try:
            user_id = _resolve_user_id(cred.credentials)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if user.status != UserStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active")

    return user
