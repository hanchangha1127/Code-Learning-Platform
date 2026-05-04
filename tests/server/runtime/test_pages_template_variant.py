from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from server.app import app


class ReactSpaPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def assert_react_entry(self, path: str, *, template_variant: str = "react") -> None:
        response = self.client.get(path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-template-variant"), template_variant)
        self.assertNotIn("User-Agent", response.headers.get("vary", ""))
        self.assertIn('id="root"', response.text)
        self.assertIn("/assets/index-", response.text)
        self.assertRegex(response.text, r"/assets/index-[^\"']+\.(?:js|css)\?v=[0-9a-f]+")
        self.assertRegex(response.headers.get("x-request-id", ""), r"^[0-9a-f]{32}$")

    def test_user_routes_return_react_spa_entry(self) -> None:
        for path in (
            "/",
            "/index.html",
            "/dashboard.html",
            "/profile.html",
            "/analysis.html",
            "/codeblock.html",
            "/arrange.html",
            "/auditor.html",
            "/refactoring-choice.html",
            "/code-blame.html",
            "/single-file-analysis.html",
            "/multi-file-analysis.html",
            "/fullstack-analysis.html",
        ):
            with self.subTest(path=path):
                self.assert_react_entry(path)

    def test_admin_route_uses_same_react_entry_with_responsive_header(self) -> None:
        self.assert_react_entry("/admin.html", template_variant="responsive")

    def test_app_route_keeps_dashboard_redirect(self) -> None:
        response = self.client.get("/app.html", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/dashboard.html")

    def test_missing_template_returns_404(self) -> None:
        response = self.client.get("/unknown-page-does-not-exist.html")
        self.assertEqual(response.status_code, 404)

    def test_removed_codecalc_page_returns_404(self) -> None:
        response = self.client.get("/codecalc.html")
        self.assertEqual(response.status_code, 404)

    def test_react_public_assets_are_served(self) -> None:
        favicon = self.client.get("/favicon.svg")
        icons = self.client.get("/icons.svg")

        self.assertEqual(favicon.status_code, 200)
        self.assertEqual(icons.status_code, 200)
        self.assertIn("image/svg+xml", favicon.headers.get("content-type", ""))
        self.assertIn("image/svg+xml", icons.headers.get("content-type", ""))


if __name__ == "__main__":
    unittest.main()
