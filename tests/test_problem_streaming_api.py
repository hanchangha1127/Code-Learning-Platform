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
from app.main import app as platform_app
from server_runtime.webapp import app


class ProblemStreamingApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        platform_app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        platform_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1,
            username="stream-test-user",
            email="stream@example.com",
            role="user",
            status="active",
        )

    def tearDown(self) -> None:
        platform_app.dependency_overrides.clear()

    def test_streaming_problem_endpoints_emit_sse_events(self) -> None:
        scenarios = [
            {
                "path": "/platform/analysis/problem",
                "body": {"languageId": "python", "difficulty": "beginner"},
                "payload": {
                    "problemId": "analysis-1",
                    "title": "analysis",
                    "mode": "analysis",
                    "problem": {
                        "id": "analysis-1",
                        "problemId": "analysis-1",
                        "title": "analysis",
                        "mode": "analysis",
                    },
                },
            },
            {
                "path": "/platform/codeblock/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "cbk1", "title": "code block", "code": "x = [BLANK]"},
            },
            {
                "path": "/platform/arrange/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "arr1", "title": "arrange"},
            },
            {
                "path": "/platform/codecalc/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "cc1", "title": "calc", "code": "print(1)"},
            },
            {
                "path": "/platform/codeerror/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "ce1", "title": "error", "blocks": ["a", "b"]},
            },
            {
                "path": "/platform/auditor/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "a1", "title": "auditor"},
            },
            {
                "path": "/platform/context-inference/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "ci1", "title": "context"},
            },
            {
                "path": "/platform/refactoring-choice/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "rc1", "title": "refactor", "options": []},
            },
            {
                "path": "/platform/code-blame/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "cb1", "title": "blame", "commits": []},
            },
        ]

        for scenario in scenarios:
            with self.subTest(path=scenario["path"]):
                with patch(
                    "app.services.platform_public_bridge.request_mode_problem",
                    return_value=scenario["payload"],
                ):
                    response = self.client.post(
                        scenario["path"],
                        json=scenario["body"],
                        headers={"Accept": "text/event-stream"},
                    )

                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("text/event-stream", response.headers.get("content-type", ""))
                self.assertIn("event: status", response.text)
                self.assertIn("event: payload", response.text)
                self.assertIn("event: done", response.text)
                if scenario["path"] == "/platform/analysis/problem":
                    self.assertIn('"problemId": "analysis-1"', response.text)
                    self.assertIn('"problem": {"id": "analysis-1"', response.text)

    def test_problem_endpoints_keep_json_without_stream_accept(self) -> None:
        scenarios = [
            (
                "/platform/analysis/problem",
                {"languageId": "python", "difficulty": "beginner"},
                {
                    "problemId": "a1",
                    "mode": "analysis",
                    "problem": {"id": "a1", "problemId": "a1", "mode": "analysis"},
                },
            ),
            ("/platform/codeblock/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "b1"}),
            ("/platform/arrange/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "c1"}),
            ("/platform/codecalc/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "d1"}),
            ("/platform/codeerror/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "e1"}),
            ("/platform/auditor/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "f1"}),
            ("/platform/context-inference/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "g1"}),
            ("/platform/refactoring-choice/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "h1"}),
            ("/platform/code-blame/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "i1"}),
        ]

        for path, body, payload in scenarios:
            with self.subTest(path=path):
                with patch("app.services.platform_public_bridge.request_mode_problem", return_value=payload):
                    response = self.client.post(path, json=body)

                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("application/json", response.headers.get("content-type", ""))
                self.assertEqual(response.json(), payload)

    def test_streaming_problem_error_emits_error_event(self) -> None:
        with patch(
            "app.services.platform_public_bridge.request_mode_problem",
            side_effect=ValueError("bad request"),
        ):
            response = self.client.post(
                "/platform/auditor/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("event: error", response.text)
        self.assertIn("bad request", response.text)
        self.assertIn('"code": "validation_error"', response.text)


if __name__ == "__main__":
    unittest.main()
