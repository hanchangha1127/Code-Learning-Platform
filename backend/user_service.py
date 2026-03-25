from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any, Dict, Optional

from backend.config import get_settings
from backend.security import generate_token, hash_password, verify_password
from backend.skill_levels import DEFAULT_SKILL_LEVEL
from backend.user_storage import UserStorageManager


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_profile(username: str) -> Dict[str, Any]:
    now = _utcnow()
    return {
        "type": "profile",
        "username": username,
        "skill_level": DEFAULT_SKILL_LEVEL,
        "diagnostic_completed": True,
        "diagnostic_total": 0,
        "diagnostic_given": 0,
        "diagnostic_results": [],
        "pending_problems": [],
        "stats": {"attempts": 0, "correct": 0},
        "created_at": now,
        "updated_at": now,
    }


class UserService:
    """Manage user registration, authentication, and per-user storage lookups."""

    def __init__(self, storage_manager: UserStorageManager):
        self.storage_manager = storage_manager
        self.guest_ttl_seconds = get_settings().guest_ttl_seconds

    def register(self, username: str, password: str) -> bool:
        normalized = self.storage_manager.normalize_username(username or "")
        if not normalized:
            raise ValueError("아이디는 영문자, 숫자, -, _ 만 사용할 수 있고 3자 이상이어야 합니다.")
        if not password:
            raise ValueError("비밀번호를 입력해주세요.")
        if self.storage_manager.exists(normalized):
            return False

        storage = self.storage_manager.create_user_storage(normalized)
        storage.append(
            {
                "type": "user",
                "username": normalized,
                "display_name": username.strip(),
                "password_hash": hash_password(password),
                "created_at": _utcnow(),
            }
        )
        storage.append(_default_profile(normalized))
        return True

    def authenticate(self, username: str, password: str) -> Optional[str]:
        normalized = self.storage_manager.normalize_username(username or "")
        if not normalized or not self.storage_manager.exists(normalized):
            return None

        storage = self.storage_manager.get_storage(normalized)
        record = storage.find_one(lambda item: item.get("type") == "user")
        if not record:
            return None

        password_hash = record.get("password_hash", "")
        verified = bool(password_hash and verify_password(password, password_hash))

        if not verified:
            legacy_plain = record.get("password")
            if legacy_plain and legacy_plain == password:
                new_hash = hash_password(password)

                def predicate(item: Dict[str, Any]) -> bool:
                    return item.get("type") == "user"

                def updater(current: Dict[str, Any]) -> Dict[str, Any]:
                    updated = dict(current)
                    updated["password_hash"] = new_hash
                    updated.pop("password", None)
                    updated["updated_at"] = _utcnow()
                    return updated

                record = storage.update_record(predicate, updater) or record
                verified = True
            else:
                verified = False

        if not verified:
            return None

        token = generate_token(prefix=normalized)
        storage.append(
            {
                "type": "session",
                "token": token,
                "created_at": _utcnow(),
            }
        )
        return token

    def create_guest(self) -> str:
        """Create a short-lived guest user and return a session token."""

        self._cleanup_expired_guests()

        username = None
        for _ in range(5):
            suffix = generate_token()[:12]
            candidate = f"guest_{suffix}"
            normalized = self.storage_manager.normalize_username(candidate)
            if normalized and not self.storage_manager.exists(normalized):
                username = normalized
                break
        if not username:
            raise ValueError("게스트 계정을 생성할 수 없습니다.")

        storage = self.storage_manager.create_user_storage(username)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.guest_ttl_seconds)
        storage.append(
            {
                "type": "user",
                "username": username,
                "display_name": "Guest",
                "guest": True,
                "created_at": now.isoformat(),
                "last_active_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
        )
        storage.append(_default_profile(username))
        token = generate_token(prefix=username)
        storage.append(
            {
                "type": "session",
                "token": token,
                "created_at": _utcnow(),
            }
        )
        return token

    def _oauth_username(self, provider: str, provider_id: str) -> str:
        base = f"{provider}_{provider_id}".lower()
        cleaned = re.sub(r"[^a-z0-9_-]", "", base)
        normalized = self.storage_manager.normalize_username(cleaned)
        if normalized:
            return normalized
        digest = hashlib.sha256(base.encode("utf-8")).hexdigest()
        fallback = f"{provider}_{digest[:24]}"
        normalized = self.storage_manager.normalize_username(fallback)
        if not normalized:
            raise ValueError("OAuth 사용자 이름을 생성할 수 없습니다.")
        return normalized

    def ensure_oauth_user(
        self,
        provider: str,
        provider_id: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> str:
        if not provider or not provider_id:
            raise ValueError("OAuth 계정 정보를 확인할 수 없습니다.")
        normalized = self._oauth_username(provider, provider_id)

        if not self.storage_manager.exists(normalized):
            storage = self.storage_manager.create_user_storage(normalized)
            storage.append(
                {
                    "type": "user",
                    "username": normalized,
                    "display_name": display_name or email or normalized,
                    "provider": provider,
                    "provider_id": provider_id,
                    "email": email,
                    "created_at": _utcnow(),
                }
            )
            storage.append(_default_profile(normalized))
            return normalized

        storage = self.storage_manager.get_storage(normalized)
        record = storage.find_one(lambda item: item.get("type") == "user")
        if record:
            if record.get("provider") and record.get("provider") != provider:
                raise ValueError("이미 다른 로그인 방식으로 등록된 계정입니다.")
            if record.get("provider_id") and record.get("provider_id") != provider_id:
                raise ValueError("연결된 계정 정보가 일치하지 않습니다.")

            def predicate(item: Dict[str, Any]) -> bool:
                return item.get("type") == "user"

            def updater(current: Dict[str, Any]) -> Dict[str, Any]:
                updated = dict(current)
                updated["provider"] = provider
                updated["provider_id"] = provider_id
                if email:
                    updated["email"] = email
                if display_name:
                    updated["display_name"] = display_name
                updated["updated_at"] = _utcnow()
                return updated

            storage.update_record(predicate, updater)
        else:
            storage.append(
                {
                    "type": "user",
                    "username": normalized,
                    "display_name": display_name or email or normalized,
                    "provider": provider,
                    "provider_id": provider_id,
                    "email": email,
                    "created_at": _utcnow(),
                }
            )
            storage.append(_default_profile(normalized))

        return normalized

    def ensure_local_user(
        self,
        username: str,
        *,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        guest: bool = False,
        provider: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> str:
        normalized = self.storage_manager.normalize_username(username or "")
        if not normalized:
            raise ValueError("사용자 계정 이름이 올바르지 않습니다.")

        display = display_name or email or normalized
        now = _utcnow()

        if not self.storage_manager.exists(normalized):
            storage = self.storage_manager.create_user_storage(normalized)
            storage.append(
                {
                    "type": "user",
                    "username": normalized,
                    "display_name": display,
                    "email": email,
                    "guest": guest,
                    "provider": provider,
                    "provider_id": provider_id,
                    "created_at": now,
                }
            )
            storage.append(_default_profile(normalized))
            return normalized

        storage = self.storage_manager.get_storage(normalized)

        user_record = storage.find_one(lambda item: item.get("type") == "user")
        if user_record is None:
            storage.append(
                {
                    "type": "user",
                    "username": normalized,
                    "display_name": display,
                    "email": email,
                    "guest": guest,
                    "provider": provider,
                    "provider_id": provider_id,
                    "created_at": now,
                }
            )
        else:
            updates: Dict[str, Any] = {}

            if display_name:
                if user_record.get("display_name") != display_name:
                    updates["display_name"] = display_name
            elif not user_record.get("display_name"):
                updates["display_name"] = display

            if email and not user_record.get("email"):
                updates["email"] = email

            if guest and user_record.get("guest") is not True:
                updates["guest"] = True

            if provider and not user_record.get("provider"):
                updates["provider"] = provider

            if provider_id and not user_record.get("provider_id"):
                updates["provider_id"] = provider_id

            if updates:
                updates["updated_at"] = now

                def predicate(item: Dict[str, Any]) -> bool:
                    return item.get("type") == "user"

                def updater(current: Dict[str, Any]) -> Dict[str, Any]:
                    updated = dict(current)
                    updated.update(updates)
                    return updated

                storage.update_record(predicate, updater)

        profile = storage.find_one(lambda item: item.get("type") == "profile")
        if profile is None:
            storage.append(_default_profile(normalized))

        return normalized

    def issue_token(self, username: str) -> str:
        normalized = self.storage_manager.normalize_username(username or "")
        if not normalized or not self.storage_manager.exists(normalized):
            raise ValueError("사용자 계정을 찾을 수 없습니다.")
        storage = self.storage_manager.get_storage(normalized)
        token = generate_token(prefix=normalized)
        storage.append(
            {
                "type": "session",
                "token": token,
                "created_at": _utcnow(),
            }
        )
        return token

    def get_user_by_token(self, token: str, max_age_seconds: int | None = None) -> Optional[str]:
        username, sep, _ = token.partition(":")
        if sep != ":":
            return None
        normalized = self.storage_manager.normalize_username(username)
        if not normalized or not self.storage_manager.exists(normalized):
            return None
        storage = self.storage_manager.get_storage(normalized)
        session = storage.find_one(lambda item: item.get("type") == "session" and item.get("token") == token)
        if not session:
            return None

        if max_age_seconds is not None:
            max_age = max(int(max_age_seconds), 0)
            if max_age <= 0:
                return None
            created_raw = session.get("created_at")
            created_at = _parse_iso(created_raw if isinstance(created_raw, str) else None)
            if created_at is None:
                return None
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
            if age_seconds > max_age:
                return None

        user_record = storage.find_one(lambda item: item.get("type") == "user")
        if user_record and user_record.get("guest") is True:
            if self._guest_expired(user_record):
                self.storage_manager.delete_storage(normalized)
                return None
            self._touch_guest(storage)
        return normalized

    def get_user_info(self, username: str) -> Dict[str, Any]:
        storage = self.storage_manager.get_storage(username)
        record = storage.find_one(lambda item: item.get("type") == "user") or {}
        return {
            "username": record.get("username") or username,
            "display_name": record.get("display_name") or record.get("email") or username,
            "provider": record.get("provider"),
            "email": record.get("email"),
            "guest": bool(record.get("guest")),
        }

    def _guest_expired(self, user_record: Dict[str, Any]) -> bool:
        expires_raw = user_record.get("expires_at")
        expires_at = None
        if isinstance(expires_raw, str):
            try:
                expires_at = datetime.fromisoformat(expires_raw)
            except ValueError:
                return True
        return bool(expires_at and datetime.now(timezone.utc) >= expires_at)

    def _touch_guest(self, storage) -> None:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.guest_ttl_seconds)

        def predicate(item: Dict[str, Any]) -> bool:
            return item.get("type") == "user"

        def updater(current: Dict[str, Any]) -> Dict[str, Any]:
            updated = dict(current)
            updated["last_active_at"] = now.isoformat()
            updated["expires_at"] = expires_at.isoformat()
            return updated

        storage.update_record(predicate, updater)

    def _cleanup_expired_guests(self) -> None:
        for username in self.storage_manager.list_users():
            if not username.startswith("guest_"):
                continue
            try:
                storage = self.storage_manager.get_storage(username)
            except FileNotFoundError:
                continue
            user_record = storage.find_one(lambda item: item.get("type") == "user")
            if user_record and user_record.get("guest") is True:
                if self._guest_expired(user_record):
                    self.storage_manager.delete_storage(username)
