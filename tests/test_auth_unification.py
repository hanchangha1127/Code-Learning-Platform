import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

# Ensure settings validation passes during imports.
os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.api.security_deps import get_current_user
from app.core.security import create_access_token
from app.db.models import UserStatus
from server_runtime.webapp import app


class _FakeQuery:
    def __init__(self, user):
        self._user = user

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._user


class _FakeDB:
    def __init__(self, user):
        self._user = user

    def query(self, _model):
        return _FakeQuery(self._user)


class UnifiedAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @patch("server_runtime.routes.auth._issue_guest_jwt", return_value="jwt.mock.token")
    def test_guest_endpoint_returns_bridge_token(self, _mock_issue):
        response = self.client.post("/api/auth/guest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("token"), "jwt.mock.token")

    @patch("server_runtime.deps.user_service.get_user_by_token", return_value=None)
    @patch("server_runtime.deps.resolve_username_from_access_token", return_value="guest_test")
    @patch("server_runtime.deps.user_service.ensure_local_user", return_value="guest_test")
    @patch(
        "server_runtime.routes.learning.user_service.get_user_info",
        return_value={"username": "guest_test", "display_name": "Guest", "guest": True},
    )
    def test_api_me_accepts_jwt_and_bootstraps_local_user(
        self,
        _mock_info,
        _mock_ensure,
        _mock_resolve,
        _mock_legacy,
    ):
        response = self.client.get("/api/me", headers={"Authorization": "Bearer jwt.mock.token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("username"), "guest_test")

    @patch("server_runtime.deps.user_service.get_user_by_token", return_value="legacy_user")
    @patch(
        "server_runtime.routes.learning.user_service.get_user_info",
        return_value={"username": "legacy_user", "display_name": "Legacy", "guest": False},
    )
    @patch(
        "server_runtime.deps.settings",
        new=SimpleNamespace(
            allow_legacy_jsonl_tokens=True,
            legacy_token_sunset_date="2026-03-31",
        ),
    )
    def test_legacy_token_sets_deprecation_headers(self, _mock_info, _mock_legacy):
        response = self.client.get("/api/me", headers={"Authorization": "Bearer legacy_user:token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-auth-legacy-token"), "true")
        self.assertEqual(response.headers.get("x-auth-legacy-sunset-date"), "2026-03-31")

    def test_platform_security_dep_accepts_access_jwt(self):
        token = create_access_token(7)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = SimpleNamespace(id=7, status=UserStatus.active)
        db = _FakeDB(user)

        resolved = get_current_user(cred=cred, db=db)
        self.assertEqual(resolved.id, 7)


if __name__ == "__main__":
    unittest.main()
