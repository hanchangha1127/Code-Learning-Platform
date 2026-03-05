from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.db.models import PreferredDifficulty
from app.main import app as platform_backend_app
from server_runtime.webapp import app


class PlatformMeSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        platform_backend_app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        platform_backend_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=77)

    def tearDown(self) -> None:
        platform_backend_app.dependency_overrides.clear()

    def test_get_settings_creates_defaults_when_row_missing(self) -> None:
        with (
            patch("app.api.routes.me.get_settings", return_value=None) as mock_get_settings,
            patch(
                "app.api.routes.me.update_settings",
                return_value=SimpleNamespace(
                    preferred_language="python",
                    preferred_difficulty=PreferredDifficulty.medium,
                ),
            ) as mock_update_settings,
        ):
            response = self.client.get("/platform/me/settings")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {
                "preferred_language": "python",
                "preferred_difficulty": "medium",
            },
        )
        mock_get_settings.assert_called_once()
        mock_update_settings.assert_called_once()
        args = mock_update_settings.call_args.args
        kwargs = mock_update_settings.call_args.kwargs
        self.assertEqual(args[1], 77)
        self.assertEqual(kwargs["preferred_language"], "python")
        self.assertEqual(kwargs["preferred_difficulty"], PreferredDifficulty.medium)


if __name__ == "__main__":
    unittest.main()
