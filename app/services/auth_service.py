# app/services/auth_service.py
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    non_refresh_session_expires_at,
    refresh_expires_at,
    verify_password,
)
from app.db.base import utcnow
from app.db.models import PreferredDifficulty, User, UserSession, UserSettings, UserStatus


def _create_user_session(db: Session, user_id: int) -> tuple[UserSession, str]:
    refresh = create_refresh_token()
    session = UserSession(
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(refresh),
        expires_at=refresh_expires_at(),
        revoked_at=None,
    )
    db.add(session)
    db.flush()
    return session, refresh


def issue_non_refreshable_access_token(db: Session, user_id: int) -> str:
    now = utcnow()
    (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            or_(
                UserSession.expires_at <= now,
                UserSession.revoked_at.isnot(None),
            ),
        )
        .delete(synchronize_session=False)
    )
    session = UserSession(
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(create_refresh_token()),
        expires_at=non_refresh_session_expires_at(),
        revoked_at=None,
    )
    db.add(session)
    db.flush()
    return create_access_token(user_id, session_id=session.id)


def _revoke_user_session(db: Session, *, session_id: int, user_id: int | None = None) -> bool:
    filters = [
        UserSession.id == session_id,
        UserSession.revoked_at.is_(None),
    ]
    if user_id is not None:
        filters.append(UserSession.user_id == user_id)

    session = db.query(UserSession).filter(and_(*filters)).first()
    if session is None:
        return False

    session.revoked_at = utcnow()
    return True


def _session_id_from_access_token(access_token: str | None) -> tuple[int, int] | None:
    if not access_token:
        return None
    try:
        payload = decode_access_token(access_token)
        if payload.get("type") != "access":
            return None
        session_id = int(payload.get("sid"))
        user_id = int(payload.get("sub"))
    except Exception:
        return None
    return session_id, user_id


def _raise_signup_conflict(db: Session, *, email: str, username: str, exc: IntegrityError) -> None:
    db.rollback()
    if db.query(User).filter(User.email == email).first():
        raise ValueError("email already exists") from exc
    if db.query(User).filter(User.username == username).first():
        raise ValueError("username already exists") from exc
    raise ValueError("account already exists") from exc


def signup(db: Session, email: str, username: str, password: str) -> User:
    if db.query(User).filter(User.email == email).first():
        raise ValueError("email already exists")
    if db.query(User).filter(User.username == username).first():
        raise ValueError("username already exists")

    user = User(email=email, username=username, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        _raise_signup_conflict(db, email=email, username=username, exc=exc)

    db.add(
        UserSettings(
            user_id=user.id,
            preferred_language="python",
            preferred_difficulty=PreferredDifficulty.medium,
        )
    )

    try:
        db.commit()
    except IntegrityError as exc:
        _raise_signup_conflict(db, email=email, username=username, exc=exc)
    db.refresh(user)
    return user


def login(db: Session, username: str, password: str) -> tuple[str, str]:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("invalid credentials")

    if user.status != UserStatus.active:
        raise ValueError("account is not active")

    session, refresh = _create_user_session(db, user.id)
    access = create_access_token(user.id, session_id=session.id)
    db.commit()

    return access, refresh


def refresh_tokens(db: Session, refresh_token: str) -> tuple[str, str]:
    token_hash = hash_refresh_token(refresh_token)
    now = utcnow()

    session = (
        db.query(UserSession)
        .join(User, User.id == UserSession.user_id)
        .filter(
            and_(
                UserSession.refresh_token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                User.status == UserStatus.active,
            )
        )
        .first()
    )

    if not session:
        raise ValueError("invalid refresh token")

    # Rotate refresh token: revoke current token and issue a new pair.
    session.revoked_at = now
    user_id = session.user_id
    new_session, new_refresh = _create_user_session(db, user_id)
    new_access = create_access_token(user_id, session_id=new_session.id)
    db.commit()

    return new_access, new_refresh


def logout(
    db: Session,
    refresh_token: str | None = None,
    *,
    access_token: str | None = None,
    session_id: int | None = None,
    user_id: int | None = None,
) -> None:
    changed = False

    if refresh_token:
        token_hash = hash_refresh_token(refresh_token)
        session = (
            db.query(UserSession)
            .filter(
                and_(
                    UserSession.refresh_token_hash == token_hash,
                    UserSession.revoked_at.is_(None),
                )
            )
            .first()
        )
        if session is not None:
            session.revoked_at = utcnow()
            changed = True

    if session_id is not None:
        changed = _revoke_user_session(db, session_id=session_id, user_id=user_id) or changed

    resolved_session = _session_id_from_access_token(access_token)
    if resolved_session is not None:
        resolved_session_id, resolved_user_id = resolved_session
        changed = _revoke_user_session(
            db,
            session_id=resolved_session_id,
            user_id=resolved_user_id,
        ) or changed

    if changed:
        db.commit()
