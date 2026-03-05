from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import decode_access_token
from app.db.models import User, UserStatus

bearer = HTTPBearer()


def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = cred.credentials
    try:
        payload = decode_access_token(token)
        if payload.get("type") != "access":
            raise ValueError("invalid token type")
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if user.status != UserStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active")

    return user
