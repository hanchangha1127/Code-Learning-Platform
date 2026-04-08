import os
import unittest

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from server.core.config import Settings


class AppConfigTests(unittest.TestCase):
    def test_database_url_escapes_special_characters_in_password(self):
        settings = Settings(
            DB_HOST="db.example.internal",
            DB_PORT=3307,
            DB_NAME="code_platform",
            DB_USER="appuser",
            DB_PASSWORD="p@ss:/#?word",
            JWT_SECRET="x" * 32,
        )

        self.assertEqual(
            settings.DATABASE_URL,
            "mysql+pymysql://appuser:p%40ss%3A%2F%23%3Fword@db.example.internal:3307/code_platform",
        )

    def test_admin_throttle_backend_is_normalized_to_lowercase(self):
        settings = Settings(
            DB_HOST="db.example.internal",
            DB_PORT=3307,
            DB_NAME="code_platform",
            DB_USER="appuser",
            DB_PASSWORD="password",
            JWT_SECRET="x" * 32,
            ADMIN_THROTTLE_BACKEND="MEMORY",
        )

        self.assertEqual(settings.ADMIN_THROTTLE_BACKEND, "memory")

    def test_sidless_cookie_compat_defaults_match_rollout_plan(self):
        settings = Settings(
            DB_HOST="db.example.internal",
            DB_PORT=3307,
            DB_NAME="code_platform",
            DB_USER="appuser",
            DB_PASSWORD="password",
            JWT_SECRET="x" * 32,
        )

        self.assertEqual(settings.ALLOW_SIDLESS_COOKIE_COMPAT, False)
        self.assertEqual(settings.SIDLESS_COOKIE_SUNSET_AT, "2026-04-03T23:59:59+09:00")


if __name__ == "__main__":
    unittest.main()

