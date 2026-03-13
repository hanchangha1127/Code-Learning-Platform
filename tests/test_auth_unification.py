import os
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.core.security import create_access_token
from app.db.models import UserStatus
from server_runtime.context import decode_state, encode_state, oauth_success_page
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

    def setUp(self) -> None:
        from app.main import app as platform_backend_app

        platform_backend_app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        platform_backend_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=7,
            username="platform_user",
            email="platform@example.com",
            role="user",
            status="active",
        )

    def tearDown(self) -> None:
        from app.main import app as platform_backend_app

        platform_backend_app.dependency_overrides.clear()

    @patch("app.api.routes.auth.runtime_auth_routes._issue_guest_jwt", return_value="jwt.mock.token")
    def test_platform_guest_endpoint_returns_bridge_token(self, _mock_issue):
        response = self.client.post("/platform/auth/guest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("token"), "jwt.mock.token")
        self.assertIn("code_learning_access=", response.headers.get("set-cookie", ""))

    def test_legacy_api_auth_route_returns_410_guidance(self):
        response = self.client.post("/api/auth/guest")
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(response.json().get("code"), "moved_to_platform")
        self.assertEqual(response.json().get("newPath"), "/platform/auth/guest")

    def test_legacy_guest_start_route_returns_410_guidance(self):
        response = self.client.get("/api/auth/guest/start")
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(response.json().get("newPath"), "/platform/auth/guest/start")

    def test_platform_me_route_is_available(self):
        response = self.client.get("/platform/me")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json().get("username"), "platform_user")

    def test_platform_security_dep_accepts_access_jwt(self):
        token = create_access_token(7)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = SimpleNamespace(id=7, status=UserStatus.active)
        db = _FakeDB(user)
        request = SimpleNamespace(cookies={})

        resolved = get_current_user(request=request, cred=cred, db=db)
        self.assertEqual(resolved.id, 7)

    def test_platform_password_auth_routes_are_disabled_by_default(self):
        response = self.client.post(
            "/platform/auth/login",
            json={"username": "demo", "password": "demo-password"},
        )
        self.assertEqual(response.status_code, 410, response.text)

    def test_oauth_state_next_path_blocks_scheme_relative_redirect(self):
        state = encode_state("//evil.example/path")
        self.assertEqual(decode_state(state), "/dashboard.html")

    def test_oauth_state_next_path_blocks_full_url_redirect(self):
        state = encode_state("https://evil.example/path")
        self.assertEqual(decode_state(state), "/dashboard.html")

    def test_oauth_success_page_does_not_embed_jwt_in_html(self):
        response = oauth_success_page("jwt.mock.token", "/dashboard.html")
        html = response.body.decode("utf-8")
        self.assertNotIn("jwt.mock.token", html)
        self.assertIn("cookie-session", html)

    @patch("server_runtime.context.require_google_oauth_settings", return_value=("client-id", "client-secret"))
    def test_platform_google_start_uses_localhost_redirect_uri(self, _mock_oauth):
        response = self.client.get(
            "/platform/auth/google/start",
            headers={"host": "localhost:8000"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302, response.text)
        location = response.headers["location"]
        redirect_uri = parse_qs(urlsplit(location).query)["redirect_uri"][0]
        self.assertEqual(redirect_uri, "http://localhost:8000/platform/auth/google/callback")

    @patch("server_runtime.context.require_google_oauth_settings", return_value=("client-id", "client-secret"))
    def test_platform_google_start_respects_forwarded_headers(self, _mock_oauth):
        response = self.client.get(
            "/platform/auth/google/start",
            headers={
                "host": "localhost:8000",
                "x-forwarded-proto": "https",
                "x-forwarded-host": "hhtj.site",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302, response.text)
        location = response.headers["location"]
        redirect_uri = parse_qs(urlsplit(location).query)["redirect_uri"][0]
        self.assertEqual(redirect_uri, "https://hhtj.site/platform/auth/google/callback")

    @patch("server_runtime.context.require_google_oauth_settings", return_value=("client-id", "client-secret"))
    def test_platform_google_start_rejects_unapproved_redirect_uri(self, _mock_oauth):
        response = self.client.get(
            "/platform/auth/google/start",
            headers={"host": "unapproved.example.com"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertIn("허용 목록", response.json().get("detail", ""))


    @patch("server_runtime.context.require_google_oauth_settings", return_value=("client-id", "client-secret"))
    def test_platform_google_start_uses_https_request_scheme_directly(self, _mock_oauth):
        with TestClient(app, base_url="https://hhtj.site") as https_client:
            response = https_client.get("/platform/auth/google/start", follow_redirects=False)

        self.assertEqual(response.status_code, 302, response.text)
        location = response.headers["location"]
        redirect_uri = parse_qs(urlsplit(location).query)["redirect_uri"][0]
        self.assertEqual(redirect_uri, "https://hhtj.site/platform/auth/google/callback")


if __name__ == "__main__":
    unittest.main()
