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


class PageTemplateVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @staticmethod
    def _desktop_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

    @staticmethod
    def _mobile_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.4 Mobile/15E148 Safari/604.1"
            )
        }

    def test_dashboard_route_uses_desktop_template_for_desktop_ua(self) -> None:
        response = self.client.get("/dashboard.html", headers=self._desktop_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-template-variant"), "desktop")
        self.assertIn("User-Agent", response.headers.get("vary", ""))
        self.assertIn('data-template-variant="desktop"', response.text)
        self.assertIn('id="dashboard-mode-tabs"', response.text)
        self.assertIn('id="dashboard-mode-panel-advanced"', response.text)
        self.assertRegex(response.text, r"/static/assets/css/desktop\.css\?v=[0-9a-f]+")

    def test_dashboard_route_uses_mobile_template_for_mobile_ua(self) -> None:
        response = self.client.get("/dashboard.html", headers=self._mobile_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-template-variant"), "mobile")
        self.assertIn("User-Agent", response.headers.get("vary", ""))
        self.assertIn('data-template-variant="mobile"', response.text)
        self.assertIn('id="dashboard-mode-tabs"', response.text)
        self.assertIn('id="dashboard-mode-panel-advanced"', response.text)
        self.assertRegex(response.text, r"/static/assets/css/mobile\.css\?v=[0-9a-f]+")

    def test_advanced_analysis_routes_use_desktop_template_for_desktop_ua(self) -> None:
        for path in ("/single-file-analysis.html", "/multi-file-analysis.html", "/fullstack-analysis.html"):
            with self.subTest(path=path):
                response = self.client.get(path, headers=self._desktop_headers())

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get("x-template-variant"), "desktop")
                self.assertIn("User-Agent", response.headers.get("vary", ""))
                self.assertIn('data-template-variant="desktop"', response.text)
                self.assertIn('id="advanced-analysis-shell"', response.text)
                self.assertIn('id="advanced-file-rail"', response.text)
                self.assertIn('id="advanced-load-btn"', response.text)
                self.assertIn('id="advanced-problem-title"', response.text)
                self.assertIn('id="advanced-result-panel"', response.text)
                self.assertRegex(response.text, r"/static/assets/js/widgets/review_resume\.js\?v=[0-9a-f]+")

    def test_advanced_analysis_routes_use_mobile_template_for_mobile_ua(self) -> None:
        for path in ("/single-file-analysis.html", "/multi-file-analysis.html", "/fullstack-analysis.html"):
            with self.subTest(path=path):
                response = self.client.get(path, headers=self._mobile_headers())

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get("x-template-variant"), "mobile")
                self.assertIn("User-Agent", response.headers.get("vary", ""))
                self.assertIn('data-template-variant="mobile"', response.text)
                self.assertIn('id="advanced-analysis-shell"', response.text)
                self.assertIn('id="advanced-file-strip"', response.text)
                self.assertIn('id="advanced-load-btn"', response.text)
                self.assertIn('id="advanced-problem-title"', response.text)
                self.assertIn('id="advanced-result-panel"', response.text)
                self.assertRegex(response.text, r"/static/assets/js/widgets/review_resume\.js\?v=[0-9a-f]+")

    def test_root_route_varies_on_user_agent_for_mobile_template(self) -> None:
        response = self.client.get("/", headers=self._mobile_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-template-variant"), "mobile")
        self.assertIn("User-Agent", response.headers.get("vary", ""))
        self.assertIn('data-template-variant="mobile"', response.text)

    def test_template_renderer_injects_versioned_static_assets(self) -> None:
        response = self.client.get("/dashboard.html", headers=self._desktop_headers())

        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.text, r"/static/assets/css/base\.css\?v=[0-9a-f]+")
        self.assertRegex(response.text, r"/static/assets/css/app\.css\?v=[0-9a-f]+")
        self.assertRegex(response.text, r"/static/assets/css/whiteboard-theme\.css\?v=[0-9a-f]+")
        self.assertRegex(response.text, r"/static/assets/css/desktop\.css\?v=[0-9a-f]+")
        self.assertRegex(response.text, r"/static/assets/js/pages/dashboard\.js\?v=[0-9a-f]+")

    def test_advanced_analysis_template_injects_versioned_shared_js(self) -> None:
        response = self.client.get("/single-file-analysis.html", headers=self._desktop_headers())

        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.text, r"/static/assets/js/core/api_client\.js\?v=[0-9a-f]+")
        self.assertRegex(response.text, r"/static/assets/js/core/problem_stream_client\.js\?v=[0-9a-f]+")
        self.assertRegex(response.text, r"/static/assets/js/widgets/review_resume\.js\?v=[0-9a-f]+")
        self.assertRegex(response.text, r"/static/assets/js/widgets/advanced_analysis_shell\.js\?v=[0-9a-f]+")

    def test_runtime_pages_include_request_id_header(self) -> None:
        response = self.client.get("/dashboard.html", headers=self._desktop_headers())

        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.headers.get("x-request-id", ""), r"^[0-9a-f]{32}$")

    def test_missing_template_returns_404(self) -> None:
        response = self.client.get("/unknown-page-does-not-exist.html")
        self.assertEqual(response.status_code, 404)

    def test_removed_codecalc_page_returns_404(self) -> None:
        response = self.client.get("/codecalc.html", headers=self._desktop_headers())
        self.assertEqual(response.status_code, 404)

    def test_admin_route_uses_responsive_template(self) -> None:
        response = self.client.get("/admin.html")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-template-variant"), "responsive")
        self.assertNotIn("User-Agent", response.headers.get("vary", ""))
        self.assertIn('data-template-variant="responsive"', response.text)


if __name__ == "__main__":
    unittest.main()

