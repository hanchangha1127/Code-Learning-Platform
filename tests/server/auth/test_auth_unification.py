import os
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from fastapi import HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from server.dependencies import get_db
from server.features.auth.dependencies import get_current_user
from server.core.config import Settings
from server.core.security import create_access_token
from server.db.models import UserSession, UserStatus
import server.dependencies as runtime_deps
import server.features.auth.legacy_api as runtime_auth_routes
from server.bootstrap import decode_state, encode_state, oauth_success_page
from server.app import _credentialed_cors_origins, _resolve_moved_api_path, app


class _FakeDB:
    def __init__(self, user, sessions=None):
        self._users = user if isinstance(user, dict) else {getattr(user, "id", 0): user}
        self._sessions = sessions or {}
        self.commit_calls = 0

    def query(self, model):
        return _FakeQuery(self, model)

    def commit(self):
        self.commit_calls += 1


class _FakeQuery:
    def __init__(self, db, model):
        self._db = db
        self._model = model
        self._filters = []

    def filter(self, *args, **_kwargs):
        self._filters.extend(args)
        return self

    def first(self):
        if self._model is UserSession:
            return self._resolve_session()
        return self._resolve_user()

    def _resolve_user(self):
        requested_user_id = None
        for candidate in self._filters:
            field = getattr(getattr(candidate, "left", None), "key", None)
            if field == "id":
                requested_user_id = getattr(getattr(candidate, "right", None), "value", None)
        if requested_user_id is None:
            return next(iter(self._db._users.values()), None)
        return self._db._users.get(requested_user_id)

    def _resolve_session(self):
        requested_session_id = None
        requested_user_id = None
        for candidate in self._filters:
            field = getattr(getattr(candidate, "left", None), "key", None)
            if field == "id":
                requested_session_id = getattr(getattr(candidate, "right", None), "value", None)
            if field == "user_id":
                requested_user_id = getattr(getattr(candidate, "right", None), "value", None)
        session = self._db._sessions.get(requested_session_id)
        if session is None:
            return None
        if requested_user_id is not None and getattr(session, "user_id", None) != requested_user_id:
            return None
        return session


class UnifiedAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        from server.app import platform_app as platform_backend_app

        platform_backend_app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        platform_backend_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=7,
            username="platform_user",
            email="platform@example.com",
            role="user",
            status="active",
        )

    def tearDown(self) -> None:
        from server.app import platform_app as platform_backend_app

        platform_backend_app.dependency_overrides.clear()

    @patch("server.features.auth.api.runtime_auth_routes._issue_guest_jwt", return_value="jwt.mock.token")
    def test_platform_guest_endpoint_returns_bridge_token(self, _mock_issue):
        response = self.client.post("/platform/auth/guest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("token"), "jwt.mock.token")
        self.assertIn("code_learning_access=", response.headers.get("set-cookie", ""))

    @patch("server.features.auth.api.logout")
    def test_platform_logout_revokes_refresh_token_even_when_password_auth_disabled(self, mock_logout):
        response = self.client.post(
            "/platform/auth/logout",
            json={"refresh_token": "x" * 32},
        )
        self.assertEqual(response.status_code, 200, response.text)
        mock_logout.assert_called_once()

    def test_legacy_api_auth_route_returns_410_guidance(self):
        response = self.client.post("/api/auth/guest")
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(response.json().get("code"), "moved_to_platform")
        self.assertEqual(response.json().get("newPath"), "/platform/auth/guest")

    def test_legacy_guest_start_route_returns_410_guidance(self):
        response = self.client.get("/api/auth/guest/start")
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(response.json().get("newPath"), "/platform/auth/guest")

    def test_legacy_register_route_returns_signup_guidance(self):
        response = self.client.post("/api/auth/register")
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(response.json().get("newPath"), "/platform/auth/signup")

    def test_platform_me_route_is_available(self):
        response = self.client.get("/platform/me")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json().get("username"), "platform_user")

    def test_platform_security_dep_rejects_access_jwt_without_session_binding(self):
        token = create_access_token(7)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = SimpleNamespace(id=7, username="platform_user", status=UserStatus.active)
        db = _FakeDB(user)
        response = Response()
        request = SimpleNamespace(
            cookies={},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )

        with patch("server.features.auth.dependencies._admin_metrics") as metrics:
            with self.assertRaises(Exception):
                get_current_user(request=request, response=response, cred=cred, db=db)

        metrics.record_user_activity.assert_not_called()

    def test_platform_security_dep_accepts_active_session_bound_jwt(self):
        token = create_access_token(7, session_id=91)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = SimpleNamespace(id=7, username="platform_user", status=UserStatus.active)
        active_session = SimpleNamespace(id=91, user_id=7)
        db = _FakeDB(user, sessions={91: active_session})
        response = Response()
        request = SimpleNamespace(
            cookies={},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )

        with patch("server.features.auth.dependencies._admin_metrics") as metrics:
            resolved = get_current_user(request=request, response=response, cred=cred, db=db)

        self.assertEqual(resolved.id, 7)
        metrics.record_user_activity.assert_called_once()

    def test_platform_security_dep_rejects_revoked_session_bound_jwt(self):
        token = create_access_token(7, session_id=91)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = SimpleNamespace(id=7, username="platform_user", status=UserStatus.active)
        db = _FakeDB(user, sessions={})
        response = Response()
        request = SimpleNamespace(
            cookies={},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )

        with self.assertRaises(Exception):
            get_current_user(request=request, response=response, cred=cred, db=db)

    def test_platform_security_dep_prefers_valid_bearer_over_cookie(self):
        cookie_token = create_access_token(8, session_id=92)
        bearer_token = create_access_token(7, session_id=91)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=bearer_token)
        users = {
            7: SimpleNamespace(id=7, username="bearer_user", status=UserStatus.active),
            8: SimpleNamespace(id=8, username="cookie_user", status=UserStatus.active),
        }
        sessions = {
            91: SimpleNamespace(id=91, user_id=7),
            92: SimpleNamespace(id=92, user_id=8),
        }
        db = _FakeDB(users, sessions=sessions)
        response = Response()
        request = SimpleNamespace(
            cookies={"code_learning_access": cookie_token},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )

        with patch("server.features.auth.dependencies._admin_metrics") as metrics:
            resolved = get_current_user(request=request, response=response, cred=cred, db=db)

        self.assertEqual(resolved.id, 7)
        self.assertEqual(resolved.username, "bearer_user")
        metrics.record_user_activity.assert_called_once_with(
            username="bearer_user",
            client_id="127.0.0.1|pytest-agent",
        )

    def test_platform_security_dep_rejects_invalid_bearer_even_when_cookie_is_valid(self):
        cookie_token = create_access_token(8, session_id=92)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-valid-jwt")
        db = _FakeDB(
            {8: SimpleNamespace(id=8, username="cookie_user", status=UserStatus.active)},
            sessions={92: SimpleNamespace(id=92, user_id=8)},
        )
        response = Response()
        request = SimpleNamespace(
            cookies={"code_learning_access": cookie_token},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )

        with self.assertRaises(Exception):
            get_current_user(request=request, response=response, cred=cred, db=db)

    def test_platform_security_dep_rejects_sidless_bearer_even_when_cookie_compat_is_enabled(self):
        token = create_access_token(7)
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        db = _FakeDB(SimpleNamespace(id=7, username="platform_user", status=UserStatus.active))
        response = Response()
        request = SimpleNamespace(
            cookies={},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )

        with patch("server.features.auth.dependencies.is_sidless_cookie_compat_active", return_value=True):
            with self.assertRaises(Exception):
                get_current_user(request=request, response=response, cred=cred, db=db)

    def test_platform_security_dep_reissues_sidless_cookie_with_session_binding_during_compat_window(self):
        legacy_cookie = create_access_token(7)
        db = _FakeDB(SimpleNamespace(id=7, username="platform_user", status=UserStatus.active))
        response = Response()
        request = SimpleNamespace(
            cookies={"code_learning_access": legacy_cookie},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )

        with (
            patch("server.features.auth.dependencies.is_sidless_cookie_compat_active", return_value=True),
            patch("server.features.auth.dependencies.issue_non_refreshable_access_token", return_value="replacement.jwt"),
            patch("server.features.auth.dependencies._admin_metrics") as metrics,
        ):
            resolved = get_current_user(request=request, response=response, cred=None, db=db)

        self.assertEqual(resolved.username, "platform_user")
        self.assertEqual(db.commit_calls, 1)
        self.assertEqual(response.headers.get("x-auth-legacy-token"), "true")
        self.assertIn("code_learning_access=replacement.jwt", response.headers.get("set-cookie", ""))
        metrics.record_user_activity.assert_called_once()

    def test_platform_security_dep_rejects_sidless_cookie_after_compat_window(self):
        legacy_cookie = create_access_token(7)
        db = _FakeDB(SimpleNamespace(id=7, username="platform_user", status=UserStatus.active))
        response = Response()
        request = SimpleNamespace(
            cookies={"code_learning_access": legacy_cookie},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )

        with patch("server.features.auth.dependencies.is_sidless_cookie_compat_active", return_value=False):
            with self.assertRaises(Exception):
                get_current_user(request=request, response=response, cred=None, db=db)

    def test_guest_client_id_ignores_forwarded_for_from_untrusted_source(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="203.0.113.10"),
            headers={"x-forwarded-for": "198.51.100.77"},
        )

        self.assertEqual(runtime_auth_routes._guest_client_id(request), "203.0.113.10")

    def test_guest_client_id_uses_forwarded_for_from_trusted_proxy(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"x-forwarded-for": "198.51.100.77, 127.0.0.1"},
        )

        self.assertEqual(runtime_auth_routes._guest_client_id(request), "198.51.100.77")

    def test_guest_client_id_ignores_private_proxy_source_by_default(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="10.0.0.5"),
            headers={"x-forwarded-for": "198.51.100.77, 10.0.0.5"},
        )

        self.assertEqual(runtime_auth_routes._guest_client_id(request), "10.0.0.5")

    def test_guest_client_id_uses_forwarded_for_when_private_proxy_cidr_is_configured(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="10.0.0.5"),
            headers={"x-forwarded-for": "198.51.100.77, 10.0.0.5"},
        )

        with patch.dict(os.environ, {"CODE_PLATFORM_TRUSTED_PROXY_CIDRS": "10.0.0.0/8"}):
            self.assertEqual(runtime_auth_routes._guest_client_id(request), "198.51.100.77")

    def test_runtime_deps_reject_invalid_bearer_even_when_cookie_is_present(self):
        request = SimpleNamespace(
            cookies={"code_learning_access": "cookie-token"},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )
        response = Response()

        with patch.object(runtime_deps, "_resolve_username_from_jwt", return_value="cookie-user"):
            with self.assertRaises(HTTPException) as exc_info:
                runtime_deps.get_current_username(
                    request=request,
                    response=response,
                    authorization="Basic not-bearer",
                )

        self.assertEqual(exc_info.exception.status_code, 401)

    def test_runtime_deps_prefers_valid_bearer_over_cookie(self):
        request = SimpleNamespace(
            cookies={"code_learning_access": "cookie-token"},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )
        response = Response()

        def resolve_username(token: str) -> str | None:
            return {
                "bearer-token": "bearer-user",
                "cookie-token": "cookie-user",
            }.get(token)

        with (
            patch.object(runtime_deps, "_resolve_username_from_jwt", side_effect=resolve_username),
            patch.object(runtime_deps, "_legacy_auth_allowed_now", return_value=False),
            patch.object(runtime_deps.admin_metrics, "record_user_activity") as mock_activity,
        ):
            username = runtime_deps.get_current_username(
                request=request,
                response=response,
                authorization="Bearer bearer-token",
            )

        self.assertEqual(username, "bearer-user")
        mock_activity.assert_called_once_with(
            username="bearer-user",
            client_id="127.0.0.1|pytest-agent",
        )

    def test_runtime_deps_rejects_invalid_bearer_even_when_cookie_is_valid(self):
        request = SimpleNamespace(
            cookies={"code_learning_access": "cookie-token"},
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"user-agent": "pytest-agent"},
        )
        response = Response()

        def resolve_username(token: str) -> str | None:
            return {
                "cookie-token": "cookie-user",
            }.get(token)

        with (
            patch.object(runtime_deps, "_resolve_username_from_jwt", side_effect=resolve_username),
            patch.object(runtime_deps, "_legacy_auth_allowed_now", return_value=False),
        ):
            with self.assertRaises(HTTPException) as exc_info:
                runtime_deps.get_current_username(
                    request=request,
                    response=response,
                    authorization="Bearer invalid-token",
                )

        self.assertEqual(exc_info.exception.status_code, 401)

    def test_guest_client_id_ignores_forwarded_for_from_private_non_loopback_source_by_default(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="10.0.0.9"),
            headers={"x-forwarded-for": "198.51.100.77, 10.0.0.9"},
        )

        self.assertEqual(runtime_auth_routes._guest_client_id(request), "10.0.0.9")

    def test_platform_password_auth_routes_are_disabled_by_default(self):
        response = self.client.post(
            "/platform/auth/login",
            json={"username": "demo", "password": "demo-password"},
        )
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(
            response.json().get("detail"),
            "이메일/비밀번호 로그인은 기본적으로 비활성화되어 있습니다.",
        )

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

    @patch("server.bootstrap.require_google_oauth_settings", return_value=("client-id", "client-secret"))
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

    @patch("server.bootstrap.require_google_oauth_settings", return_value=("client-id", "client-secret"))
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

    @patch("server.bootstrap.require_google_oauth_settings", return_value=("client-id", "client-secret"))
    def test_platform_google_start_rejects_unapproved_redirect_uri(self, _mock_oauth):
        response = self.client.get(
            "/platform/auth/google/start",
            headers={"host": "unapproved.example.com"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertIn("허용 목록", response.json().get("detail", ""))


    def test_credentialed_cors_origins_drops_external_http_origin(self):
        origins = _credentialed_cors_origins(
            (
                "http://localhost:8000",
                "https://hhtj.site",
                "http://hhtj.site",
            )
        )

        self.assertEqual(origins, ["http://localhost:8000", "https://hhtj.site"])

    def test_database_url_encodes_special_characters_in_password(self):
        settings = Settings(
            DB_PASSWORD="p@ss:/word?#",
            JWT_SECRET="x" * 32,
            DB_HOST="db.example",
            DB_PORT=3307,
            DB_NAME="code_platform",
            DB_USER="appuser",
        )

        self.assertIn("appuser:p%40ss%3A%2Fword%3F%23@db.example:3307", settings.DATABASE_URL)

    def test_resolve_moved_api_path_maps_legacy_auth_routes_to_real_platform_targets(self):
        self.assertEqual(_resolve_moved_api_path("/api/auth/register"), "/platform/auth/signup")
        self.assertEqual(_resolve_moved_api_path("/api/auth/guest/start"), "/platform/auth/guest")

    @patch("server.bootstrap.require_google_oauth_settings", return_value=("client-id", "client-secret"))
    def test_platform_google_start_uses_https_request_scheme_directly(self, _mock_oauth):
        with TestClient(app, base_url="https://hhtj.site") as https_client:
            response = https_client.get("/platform/auth/google/start", follow_redirects=False)

        self.assertEqual(response.status_code, 302, response.text)
        location = response.headers["location"]
        redirect_uri = parse_qs(urlsplit(location).query)["redirect_uri"][0]
        self.assertEqual(redirect_uri, "https://hhtj.site/platform/auth/google/callback")


if __name__ == "__main__":
    unittest.main()

