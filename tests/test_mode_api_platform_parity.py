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
from app.main import app as platform_backend_app
from server_runtime.webapp import app


class PlatformModeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        platform_backend_app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        platform_backend_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1,
            username="contract-user",
            email="contract@example.com",
            role="user",
            status="active",
        )

    def tearDown(self) -> None:
        platform_backend_app.dependency_overrides.clear()

    def test_platform_problem_response_contract_keys(self):
        scenarios = [
            (
                "/platform/analysis/problem",
                {"languageId": "python", "difficulty": "beginner"},
                {
                    "problemId": "an-1",
                    "title": "Analysis problem",
                    "mode": "analysis",
                    "problem": {
                        "id": "an-1",
                        "problemId": "an-1",
                        "title": "Analysis problem",
                        "mode": "analysis",
                    },
                },
            ),
            ("/platform/codeblock/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "cb-1", "title": "Code block problem", "code": "x = [BLANK]"}),
            ("/platform/arrange/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "arr-1", "title": "Arrange problem", "blocks": ["a", "b"]}),
            ("/platform/codecalc/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "calc-1", "title": "Calc problem", "code": "print(1)"}),
            ("/platform/codeerror/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "err-1", "title": "Error problem", "blocks": ["a", "b"]}),
            ("/platform/auditor/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "aud-1", "title": "Auditor problem", "code": "pass", "prompt": "Inspect this code."}),
            ("/platform/context-inference/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "ctx-1", "title": "Context problem", "snippet": "pass", "prompt": "Infer the missing context."}),
            ("/platform/refactoring-choice/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "ref-1", "title": "Choice problem", "options": []}),
            ("/platform/code-blame/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "blame-1", "title": "Blame problem", "commits": []}),
            ("/platform/single-file-analysis/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "sfa-1", "title": "Single file analysis", "files": [{"id": "one", "path": "app/main.py", "name": "main.py", "language": "python", "role": "entrypoint", "content": "print('ok')"}]}),
            ("/platform/multi-file-analysis/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "mfa-1", "title": "Multi file analysis", "files": [{"id": "one", "path": "app/main.py", "name": "main.py", "language": "python", "role": "controller", "content": "print('ok')"}, {"id": "two", "path": "app/service.py", "name": "service.py", "language": "python", "role": "service", "content": "print('service')"}]}),
            ("/platform/fullstack-analysis/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "fsa-1", "title": "Fullstack analysis", "files": [{"id": "frontend", "path": "frontend/page.tsx", "name": "page.tsx", "language": "tsx", "role": "frontend", "content": "export function Page() { return null; }"}, {"id": "backend", "path": "backend/api.py", "name": "api.py", "language": "python", "role": "backend", "content": "def handler():\n    return None"}]}),
        ]

        for path, body, payload in scenarios:
            with self.subTest(path=path):
                with patch("app.services.platform_public_bridge.request_mode_problem", return_value=payload):
                    response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), payload)
                self.assertIn("problemId", response.json())
                if path == "/platform/analysis/problem":
                    self.assertEqual(response.json()["problem"]["problemId"], "an-1")

    def test_platform_submit_response_contract_keys(self):
        scenarios = [
            ("/platform/analysis/submit", {"languageId": "python", "problemId": "an-1", "explanation": "explain"}, {"correct": True, "score": 80, "feedback": {"summary": "Good"}}),
            ("/platform/codeblock/submit", {"problemId": "cb-1", "selectedOption": 1}, {"correct": True, "score": 100, "feedback": {"summary": "Correct"}}),
            ("/platform/arrange/submit", {"problemId": "arr-1", "order": ["a", "b"]}, {"correct": False, "score": 50, "feedback": {"summary": "Try the order again"}}),
            ("/platform/codecalc/submit", {"problemId": "calc-1", "output": "1"}, {"correct": True, "score": 100, "feedback": {"summary": "Accurate"}}),
            ("/platform/codeerror/submit", {"problemId": "err-1", "selectedIndex": 0}, {"correct": False, "score": 40, "feedback": {"summary": "Wrong option"}}),
            ("/platform/auditor/submit", {"problemId": "aud-1", "report": "report"}, {"correct": True, "score": 90, "feedback": {"summary": "Solid review"}}),
            ("/platform/context-inference/submit", {"problemId": "ctx-1", "report": "report"}, {"correct": True, "score": 90, "feedback": {"summary": "Solid review"}}),
            ("/platform/refactoring-choice/submit", {"problemId": "ref-1", "selectedOption": "A", "report": "report"}, {"correct": True, "score": 90, "feedback": {"summary": "Solid review"}}),
            ("/platform/code-blame/submit", {"problemId": "blame-1", "selectedCommits": ["B"], "report": "report"}, {"correct": True, "score": 90, "feedback": {"summary": "Solid review"}}),
            ("/platform/single-file-analysis/submit", {"problemId": "sfa-1", "report": "report"}, {"correct": True, "score": 90, "feedback": {"summary": "Solid review"}, "referenceReport": "reference", "passThreshold": 70}),
            ("/platform/multi-file-analysis/submit", {"problemId": "mfa-1", "report": "report"}, {"correct": True, "score": 90, "feedback": {"summary": "Solid review"}, "referenceReport": "reference", "passThreshold": 70}),
            ("/platform/fullstack-analysis/submit", {"problemId": "fsa-1", "report": "report"}, {"correct": True, "score": 90, "feedback": {"summary": "Solid review"}, "referenceReport": "reference", "passThreshold": 70}),
        ]

        for path, body, payload in scenarios:
            with self.subTest(path=path):
                with patch("app.services.platform_public_bridge.submit_mode_answer", return_value=payload):
                    response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), payload)
                self.assertIn("correct", response.json())

    def test_legacy_api_routes_return_410_guidance(self):
        scenarios = [
            ("/api/profile", "GET", None, "/platform/profile"),
            ("/api/languages", "GET", None, "/platform/languages"),
            ("/api/report", "GET", None, "/platform/report"),
            ("/api/diagnostics/start", "POST", {"languageId": "python", "difficulty": "beginner"}, "/platform/analysis/problem"),
            ("/api/problem/submit", "POST", {"languageId": "python", "problemId": "an-1", "explanation": "explain"}, "/platform/analysis/submit"),
            ("/api/code-block/problem", "POST", {"language": "python", "difficulty": "beginner"}, "/platform/codeblock/problem"),
            ("/api/code-arrange/problem", "POST", {"language": "python", "difficulty": "beginner"}, "/platform/arrange/problem"),
            ("/api/code-calc/problem", "POST", {"language": "python", "difficulty": "beginner"}, "/platform/codecalc/problem"),
            ("/api/code-error/problem", "POST", {"language": "python", "difficulty": "beginner"}, "/platform/codeerror/problem"),
            ("/api/auditor/problem", "POST", {"language": "python", "difficulty": "beginner"}, "/platform/auditor/problem"),
            ("/api/context-inference/problem", "POST", {"language": "python", "difficulty": "beginner"}, "/platform/context-inference/problem"),
            ("/api/refactoring-choice/problem", "POST", {"language": "python", "difficulty": "beginner"}, "/platform/refactoring-choice/problem"),
            ("/api/code-blame/problem", "POST", {"language": "python", "difficulty": "beginner"}, "/platform/code-blame/problem"),
        ]

        for path, method, body, new_path in scenarios:
            with self.subTest(path=path):
                response = self.client.request(method, path, json=body)
                self.assertEqual(response.status_code, 410, response.text)
                self.assertEqual(response.json().get("code"), "moved_to_platform")
                self.assertEqual(response.json().get("newPath"), new_path)


if __name__ == "__main__":
    unittest.main()
