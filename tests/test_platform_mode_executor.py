from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.services.platform_mode_executor import run_platform_mode_submit_background


class PlatformModeExecutorTests(unittest.TestCase):
    def test_auditor_background_submit_uses_bridge_for_runtime_problem_ids(self) -> None:
        fake_user = SimpleNamespace(username="guest_test")
        fake_db = SimpleNamespace(get=lambda model, key: fake_user, rollback=lambda: None, close=lambda: None)

        with (
            patch("app.services.platform_mode_executor.SessionLocal", return_value=fake_db),
            patch("app.services.platform_mode_executor.observe_platform_mode_operation") as mock_observe,
            patch(
                "app.services.platform_mode_executor.platform_public_bridge.submit_mode_answer",
                return_value={"verdict": "passed", "score": 91},
            ) as mock_submit,
        ):
            mock_observe.return_value.__enter__.return_value = None
            mock_observe.return_value.__exit__.return_value = None

            result = run_platform_mode_submit_background(
                "auditor",
                7,
                {"problem_id": "auditor:runtime-problem", "report": "audit report", "request_id": "req-1"},
            )

        self.assertEqual(result, {"verdict": "passed", "score": 91})
        mock_submit.assert_called_once_with(
            mode="auditor",
            username="guest_test",
            user_id=7,
            body={"problemId": "auditor:runtime-problem", "report": "audit report"},
            db=fake_db,
        )

    def test_background_submit_uses_bridge_for_supported_modes(self) -> None:
        fake_user = SimpleNamespace(username="guest_test")
        fake_db = SimpleNamespace(get=lambda model, key: fake_user, rollback=lambda: None, close=lambda: None)
        cases = [
            (
                "refactoring-choice",
                {
                    "problem_id": "refactor:runtime-problem",
                    "selected_option": "B",
                    "report": "refactor review",
                    "request_id": "req-refactor",
                },
                {
                    "problemId": "refactor:runtime-problem",
                    "selectedOption": "B",
                    "report": "refactor review",
                },
            ),
            (
                "code-blame",
                {
                    "problem_id": "blame:runtime-problem",
                    "selected_commits": ["A", "C"],
                    "report": "blame analysis",
                    "request_id": "req-blame",
                },
                {
                    "problemId": "blame:runtime-problem",
                    "selectedCommits": ["A", "C"],
                    "report": "blame analysis",
                },
            ),
        ]

        for mode, payload, expected_body in cases:
            with self.subTest(mode=mode):
                with (
                    patch("app.services.platform_mode_executor.SessionLocal", return_value=fake_db),
                    patch("app.services.platform_mode_executor.observe_platform_mode_operation") as mock_observe,
                    patch(
                        "app.services.platform_mode_executor.platform_public_bridge.submit_mode_answer",
                        return_value={"verdict": "passed", "score": 88},
                    ) as mock_submit,
                ):
                    mock_observe.return_value.__enter__.return_value = None
                    mock_observe.return_value.__exit__.return_value = None

                    result = run_platform_mode_submit_background(mode, 7, payload)

                self.assertEqual(result, {"verdict": "passed", "score": 88})
                mock_submit.assert_called_once_with(
                    mode=mode,
                    username="guest_test",
                    user_id=7,
                    body=expected_body,
                    db=fake_db,
                )

    def test_deleted_modes_are_rejected(self) -> None:
        fake_user = SimpleNamespace(username="guest_test")
        fake_db = SimpleNamespace(get=lambda model, key: fake_user, rollback=lambda: None, close=lambda: None)

        with (
            patch("app.services.platform_mode_executor.SessionLocal", return_value=fake_db),
            patch("app.services.platform_mode_executor.observe_platform_mode_operation") as mock_observe,
            patch("app.services.platform_mode_executor.platform_public_bridge.submit_mode_answer") as mock_submit,
        ):
            mock_observe.return_value.__enter__.return_value = None
            mock_observe.return_value.__exit__.return_value = None

            with self.assertRaises(ValueError):
                run_platform_mode_submit_background(
                    "context-inference",
                    7,
                    {"problem_id": "ctx:runtime-problem", "report": "removed mode", "request_id": "req-ctx"},
                )

        mock_submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
