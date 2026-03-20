import os
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.core.security import create_access_token, decode_access_token
from app.db.models import User, UserSession, UserSettings, UserStatus
from server_runtime import platform_auth


class _FakeUserQuery:
    def __init__(self, session):
        self._session = session
        self._field = None
        self._value = None

    def filter(self, expression):
        self._field = getattr(getattr(expression, "left", None), "key", None)
        self._value = getattr(getattr(expression, "right", None), "value", None)
        return self

    def first(self):
        if self._field == "username":
            if getattr(self._session.existing_user, "username", None) == self._value:
                return self._session.existing_user
            return None
        if self._field == "email":
            if self._value in self._session.existing_emails:
                return object()
            return None
        if self._field == "id":
            if getattr(self._session.existing_user, "id", None) == self._value:
                return self._session.existing_user
            return None
        return None


class _FakeSettingsQuery:
    def __init__(self, session):
        self._session = session

    def filter(self, _expression):
        return self

    def first(self):
        return object() if self._session.settings_exists else None


class _FakeUserSessionQuery:
    def __init__(self, session):
        self._session = session
        self._filters = {}

    def filter(self, *expressions):
        for expression in expressions:
            field = getattr(getattr(expression, "left", None), "key", None)
            value = getattr(getattr(expression, "right", None), "value", None)
            if field:
                self._filters[field] = value
        return self

    def first(self):
        requested_session_id = self._filters.get("id")
        requested_user_id = self._filters.get("user_id")
        for session in self._session.user_sessions:
            if requested_session_id is not None and getattr(session, "id", None) != requested_session_id:
                continue
            if requested_user_id is not None and getattr(session, "user_id", None) != requested_user_id:
                continue
            if getattr(session, "revoked_at", None) is not None:
                continue
            return session
        return None

    def delete(self, synchronize_session: bool = False):
        _ = synchronize_session
        requested_user_id = self._filters.get("user_id")
        now = datetime.now(UTC).replace(tzinfo=None)
        kept = []
        removed = 0
        for session in self._session.user_sessions:
            if requested_user_id is not None and getattr(session, "user_id", None) != requested_user_id:
                kept.append(session)
                continue
            revoked = getattr(session, "revoked_at", None) is not None
            expires_at = getattr(session, "expires_at", None)
            expired = isinstance(expires_at, datetime) and expires_at <= now
            if revoked or expired:
                removed += 1
                continue
            kept.append(session)
        self._session.user_sessions = kept
        return removed


class _FakePlatformAuthSession:
    def __init__(self, *, existing_user=None, raise_user_conflict_once=False, raise_settings_conflict_once=False):
        self.existing_user = existing_user
        self.raise_user_conflict_once = raise_user_conflict_once
        self.raise_settings_conflict_once = raise_settings_conflict_once
        self.existing_emails = {existing_user.email} if getattr(existing_user, "email", None) else set()
        self.settings_exists = False
        self.pending_user = None
        self.pending_settings = None
        self.pending_user_session = None
        self.user_sessions = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query(self, model):
        if model is User:
            return _FakeUserQuery(self)
        if model is UserSettings:
            return _FakeSettingsQuery(self)
        if model is UserSession:
            return _FakeUserSessionQuery(self)
        raise AssertionError(f"unexpected model: {model}")

    def add(self, obj):
        if isinstance(obj, User):
            self.pending_user = obj
            return
        if isinstance(obj, UserSettings):
            self.pending_settings = obj
            return
        if isinstance(obj, UserSession):
            self.pending_user_session = obj
            return
        raise AssertionError(f"unexpected add: {obj}")

    def flush(self):
        if self.pending_user is not None:
            if self.raise_user_conflict_once:
                self.raise_user_conflict_once = False
                self.existing_user = SimpleNamespace(
                    id=21,
                    username=self.pending_user.username,
                    email=self.pending_user.email,
                    status=UserStatus.active,
                )
                self.existing_emails.add(self.pending_user.email)
                self.pending_user = None
                raise IntegrityError("insert", None, Exception("duplicate user"))

            self.pending_user.id = 42
            self.existing_user = self.pending_user
            self.existing_emails.add(self.pending_user.email)
            self.pending_user = None

        if self.pending_settings is not None:
            if self.raise_settings_conflict_once:
                self.raise_settings_conflict_once = False
                self.settings_exists = True
                self.pending_settings = None
                raise IntegrityError("insert", None, Exception("duplicate settings"))

            self.settings_exists = True
            self.pending_settings = None

        if self.pending_user_session is not None:
            self.pending_user_session.id = len(self.user_sessions) + 1
            self.user_sessions.append(self.pending_user_session)
            self.pending_user_session = None

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1
        self.pending_user = None
        self.pending_settings = None
        self.pending_user_session = None


class PlatformAuthTests(unittest.TestCase):
    def test_ensure_platform_user_recovers_from_concurrent_user_create(self):
        fake_session = _FakePlatformAuthSession(raise_user_conflict_once=True)

        with patch.object(platform_auth, "SessionLocal", return_value=fake_session):
            user = platform_auth.ensure_platform_user(username="race_user")

        self.assertEqual(user.username, "race_user")
        self.assertTrue(fake_session.settings_exists)
        self.assertEqual(fake_session.rollback_calls, 1)
        self.assertEqual(fake_session.commit_calls, 1)

    def test_ensure_platform_user_recovers_from_concurrent_settings_create(self):
        existing_user = SimpleNamespace(
            id=7,
            username="settings_user",
            email="settings@example.com",
            status=UserStatus.active,
        )
        fake_session = _FakePlatformAuthSession(
            existing_user=existing_user,
            raise_settings_conflict_once=True,
        )

        with patch.object(platform_auth, "SessionLocal", return_value=fake_session):
            user = platform_auth.ensure_platform_user(username="settings_user")

        self.assertEqual(user.username, "settings_user")
        self.assertTrue(fake_session.settings_exists)
        self.assertEqual(fake_session.rollback_calls, 1)
        self.assertEqual(fake_session.commit_calls, 1)

    def test_issue_platform_access_token_creates_session_bound_jwt(self):
        existing_user = SimpleNamespace(
            id=7,
            username="guest_user",
            email="guest@example.com",
            status=UserStatus.active,
        )
        fake_session = _FakePlatformAuthSession(existing_user=existing_user)

        with patch.object(platform_auth, "SessionLocal", return_value=fake_session):
            token = platform_auth.issue_platform_access_token(username="guest_user", guest=True)

        payload = decode_access_token(token)
        self.assertEqual(payload.get("sub"), "7")
        self.assertEqual(payload.get("sid"), "1")
        self.assertEqual(len(fake_session.user_sessions), 1)

    def test_issue_platform_access_token_uses_non_refreshable_session_expiry(self):
        existing_user = SimpleNamespace(
            id=7,
            username="guest_user",
            email="guest@example.com",
            status=UserStatus.active,
        )
        fake_session = _FakePlatformAuthSession(existing_user=existing_user)
        sentinel_expiry = object()

        with patch.object(platform_auth, "SessionLocal", return_value=fake_session), patch(
            "app.services.auth_service.non_refresh_session_expires_at",
            return_value=sentinel_expiry,
        ):
            platform_auth.issue_platform_access_token(username="guest_user", guest=True)

        self.assertIs(fake_session.user_sessions[0].expires_at, sentinel_expiry)

    def test_issue_platform_access_token_uses_short_lived_non_refreshable_session(self):
        existing_user = SimpleNamespace(
            id=7,
            username="guest_user",
            email="guest@example.com",
            status=UserStatus.active,
        )
        fake_session = _FakePlatformAuthSession(existing_user=existing_user)

        with patch.object(platform_auth, "SessionLocal", return_value=fake_session):
            platform_auth.issue_platform_access_token(username="guest_user", guest=True)

        expires_at = fake_session.user_sessions[0].expires_at
        self.assertIsInstance(expires_at, datetime)
        self.assertLess(expires_at - datetime.now(UTC).replace(tzinfo=None), timedelta(hours=1))

    def test_resolve_username_from_access_token_rejects_revoked_session(self):
        existing_user = SimpleNamespace(
            id=7,
            username="guest_user",
            email="guest@example.com",
            status=UserStatus.active,
        )
        fake_session = _FakePlatformAuthSession(existing_user=existing_user)
        revoked_session = UserSession(
            user_id=7,
            refresh_token_hash="revoked",
            expires_at=SimpleNamespace(),
            revoked_at=SimpleNamespace(),
        )
        revoked_session.id = 91
        fake_session.user_sessions.append(revoked_session)
        token = create_access_token(7, session_id=91)

        with patch.object(platform_auth, "SessionLocal", return_value=fake_session):
            resolved = platform_auth.resolve_username_from_access_token(token)

        self.assertIsNone(resolved)

    def test_resolve_username_from_access_token_rejects_token_without_session_binding(self):
        token = create_access_token(7)

        resolved = platform_auth.resolve_username_from_access_token(token)

        self.assertIsNone(resolved)

    def test_upgrade_legacy_access_cookie_returns_session_bound_replacement_for_active_user(self):
        existing_user = SimpleNamespace(
            id=7,
            username="guest_user",
            email="guest@example.com",
            status=UserStatus.active,
        )
        fake_session = _FakePlatformAuthSession(existing_user=existing_user)
        legacy_token = create_access_token(7)

        with patch.object(platform_auth, "SessionLocal", return_value=fake_session):
            upgraded = platform_auth.upgrade_legacy_access_cookie(legacy_token)

        self.assertIsNotNone(upgraded)
        username, replacement_token = upgraded
        payload = decode_access_token(replacement_token)
        self.assertEqual(username, "guest_user")
        self.assertEqual(payload.get("sub"), "7")
        self.assertEqual(payload.get("sid"), "1")
        self.assertEqual(fake_session.commit_calls, 1)

    def test_upgrade_legacy_access_cookie_returns_none_for_session_bound_token(self):
        session_bound = create_access_token(7, session_id=91)

        upgraded = platform_auth.upgrade_legacy_access_cookie(session_bound)

        self.assertIsNone(upgraded)

    def test_upgrade_legacy_access_cookie_returns_none_for_inactive_user(self):
        existing_user = SimpleNamespace(
            id=7,
            username="guest_user",
            email="guest@example.com",
            status=UserStatus.blocked,
        )
        fake_session = _FakePlatformAuthSession(existing_user=existing_user)
        legacy_token = create_access_token(7)

        with patch.object(platform_auth, "SessionLocal", return_value=fake_session):
            upgraded = platform_auth.upgrade_legacy_access_cookie(legacy_token)

        self.assertIsNone(upgraded)


if __name__ == "__main__":
    unittest.main()
