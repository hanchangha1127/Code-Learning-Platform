from __future__ import annotations

import os
import time
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
from app.services.platform_public_bridge import ProblemFollowUpUnavailableError
from server_runtime.routes.learning import (
    _ProblemStreamCancelled,
    _execute_stream_problem,
    _invoke_stream_problem_work,
)
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

    def test_invoke_stream_problem_work_supports_legacy_zero_arg_callables(self) -> None:
        payload_events: list[dict] = []
        partial_events: list[dict] = []

        result = _invoke_stream_problem_work(
            lambda: {"problemId": "legacy-1"},
            payload_events.append,
            partial_events.append,
        )

        self.assertEqual(result, {"problemId": "legacy-1"})
        self.assertEqual(payload_events, [])
        self.assertEqual(partial_events, [])

    def test_execute_stream_problem_preserves_internal_stream_cancellation(self) -> None:
        with self.assertRaises(_ProblemStreamCancelled):
            _execute_stream_problem("cancelled", lambda: (_ for _ in ()).throw(_ProblemStreamCancelled()))

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
                "payload": {
                    "problemId": "cbk1",
                    "title": "반복문 누적",
                    "objective": "반복문 안에서 값을 누적해 최종 합계를 완성하세요.",
                    "code": "x = [BLANK]",
                },
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
                "path": "/platform/auditor/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "a1", "title": "auditor"},
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
            {
                "path": "/platform/single-file-analysis/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "sfa1", "title": "single file", "files": [{"id": "one", "path": "app/main.py", "name": "main.py", "language": "python", "role": "entrypoint", "content": "print('ok')"}]},
            },
            {
                "path": "/platform/multi-file-analysis/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "mfa1", "title": "multi file", "files": [{"id": "one", "path": "app/main.py", "name": "main.py", "language": "python", "role": "controller", "content": "print('ok')"}, {"id": "two", "path": "app/service.py", "name": "service.py", "language": "python", "role": "service", "content": "print('service')"}]},
            },
            {
                "path": "/platform/fullstack-analysis/problem",
                "body": {"language": "python", "difficulty": "beginner"},
                "payload": {"problemId": "fsa1", "title": "fullstack", "files": [{"id": "frontend", "path": "frontend/page.tsx", "name": "page.tsx", "language": "tsx", "role": "frontend", "content": "export function Page() { return null; }"}, {"id": "backend", "path": "backend/api.py", "name": "api.py", "language": "python", "role": "backend", "content": "def handler():\n    return None"}]},
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
                self.assertIn('"persisted": true', response.text)
                if scenario["path"] == "/platform/analysis/problem":
                    self.assertIn('"problemId": "analysis-1"', response.text)
                    self.assertIn('"problem": {"id": "analysis-1"', response.text)

    def test_streaming_problem_emits_partial_events_when_backend_reports_deltas(self) -> None:
        payload = {"problemId": "stream-partial-1", "title": "partial"}

        def _stream_with_partial(**kwargs):
            emit_partial = kwargs.get("on_partial_ready")
            if callable(emit_partial):
                emit_partial({"delta": '{"title": "par'})
                emit_partial({"delta": 'tial"}'})
            emit_payload = kwargs.get("on_payload_ready")
            if callable(emit_payload):
                emit_payload(payload)
            return payload

        with patch("app.services.platform_public_bridge.request_mode_problem", side_effect=_stream_with_partial):
            response = self.client.post(
                "/platform/auditor/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("event: partial", response.text)
        self.assertIn('\\"title\\": \\"partial\\"', response.text)
        self.assertIn("event: payload", response.text)

    def test_streaming_problem_coalesces_partial_events_before_next_drain(self) -> None:
        payload = {"problemId": "stream-partial-merge-1", "title": "partial"}

        def _stream_with_burst_partials(**kwargs):
            emit_partial = kwargs.get("on_partial_ready")
            if callable(emit_partial):
                emit_partial({"delta": '{"title": "'})
                emit_partial({"delta": "merged"})
                emit_partial({"delta": '"}'})
            emit_payload = kwargs.get("on_payload_ready")
            if callable(emit_payload):
                emit_payload(payload)
            return payload

        with patch("app.services.platform_public_bridge.request_mode_problem", side_effect=_stream_with_burst_partials):
            response = self.client.post(
                "/platform/auditor/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.text.count("event: partial"), 1)
        self.assertIn('\\"title\\": \\"merged\\"', response.text)
        self.assertIn("event: payload", response.text)

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
            ("/platform/auditor/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "f1"}),
            ("/platform/refactoring-choice/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "h1"}),
            ("/platform/code-blame/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "i1"}),
            ("/platform/single-file-analysis/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "j1", "files": []}),
            ("/platform/multi-file-analysis/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "k1", "files": []}),
            ("/platform/fullstack-analysis/problem", {"language": "python", "difficulty": "beginner"}, {"problemId": "l1", "files": []}),
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
        self.assertIn('"persisted": false', response.text)

    def test_streaming_problem_timeout_emits_timeout_error_event(self) -> None:
        with patch(
            "app.services.platform_public_bridge.request_mode_problem",
            side_effect=TimeoutError("request timed out"),
        ):
            response = self.client.post(
                "/platform/auditor/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("event: error", response.text)
        self.assertIn('"code": "request_timeout"', response.text)
        self.assertIn('"httpStatus": 504', response.text)
        self.assertIn('"persisted": false', response.text)

    def test_streaming_problem_capacity_failure_emits_retryable_503_error_event(self) -> None:
        with patch(
            "app.services.platform_public_bridge.request_mode_problem",
            side_effect=ProblemFollowUpUnavailableError("stream_capacity_exceeded"),
        ):
            response = self.client.post(
                "/platform/auditor/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("event: error", response.text)
        self.assertIn('"code": "stream_capacity_exceeded"', response.text)
        self.assertIn('"httpStatus": 503', response.text)
        self.assertIn('"retryable": true', response.text)
        self.assertIn('"persisted": false', response.text)

    def test_streaming_problem_emits_persisting_status_until_follow_up_finishes(self) -> None:
        payload = {"problemId": "persist-1", "title": "persist"}

        def _delayed_success(**kwargs):
            emit_payload = kwargs.get("on_payload_ready")
            if emit_payload is not None:
                emit_payload(payload)
            time.sleep(0.3)
            return payload

        with patch("app.services.platform_public_bridge.request_mode_problem", side_effect=_delayed_success):
            response = self.client.post(
                "/platform/auditor/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('"phase": "persisting"', response.text)
        self.assertIn('"persisted": true', response.text)

    def test_non_arrange_streaming_problem_endpoints_emit_payload_before_follow_up_completes(self) -> None:
        payload = {"problemId": "persist-3", "title": "persist"}
        scenarios = [
            ("/platform/analysis/problem", {"languageId": "python", "difficulty": "beginner"}),
            ("/platform/codeblock/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/codecalc/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/single-file-analysis/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/multi-file-analysis/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/fullstack-analysis/problem", {"language": "python", "difficulty": "beginner"}),
        ]

        for path, body in scenarios:
            with self.subTest(path=path):
                def _delayed_success(**kwargs):
                    emit_payload = kwargs.get("on_payload_ready")
                    if emit_payload is not None:
                        emit_payload(payload)
                    time.sleep(0.3)
                    return payload

                with patch("app.services.platform_public_bridge.request_mode_problem", side_effect=_delayed_success):
                    response = self.client.post(
                        path,
                        json=body,
                        headers={"Accept": "text/event-stream"},
                    )

                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("event: payload", response.text)
                self.assertIn('"phase": "persisting"', response.text)
                self.assertIn('"persisted": true', response.text)

    def test_arrange_streaming_problem_endpoint_keeps_non_deferred_path(self) -> None:
        payload = {"problemId": "arr-early", "title": "arrange"}

        def _capture_kwargs(**kwargs):
            self.assertFalse(bool(kwargs.get("defer_persistence")))
            self.assertIsNone(kwargs.get("on_payload_ready"))
            return payload

        with patch("app.services.platform_public_bridge.request_mode_problem", side_effect=_capture_kwargs):
            response = self.client.post(
                "/platform/arrange/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('"phase": "persisting"', response.text)
        self.assertIn('"persisted": true', response.text)

    def test_streaming_problem_emits_late_error_when_failure_happens_after_payload(self) -> None:
        payload = {"problemId": "persist-2", "title": "persist"}

        def _late_failure(**kwargs):
            emit_payload = kwargs.get("on_payload_ready")
            if emit_payload is not None:
                emit_payload(payload)
            raise RuntimeError("follow-up failed")

        with patch("app.services.platform_public_bridge.request_mode_problem", side_effect=_late_failure):
            response = self.client.post(
                "/platform/auditor/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("event: payload", response.text)
        self.assertIn("event: error", response.text)
        self.assertIn('"ok": false', response.text)
        self.assertIn('"persisted": false', response.text)

    def test_streaming_routes_enable_deferred_payload_streaming_for_non_arrange_modes(self) -> None:
        scenarios = [
            ("/platform/analysis/problem", {"languageId": "python", "difficulty": "beginner"}),
            ("/platform/codeblock/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/codecalc/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/auditor/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/refactoring-choice/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/code-blame/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/single-file-analysis/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/multi-file-analysis/problem", {"language": "python", "difficulty": "beginner"}),
            ("/platform/fullstack-analysis/problem", {"language": "python", "difficulty": "beginner"}),
        ]

        for path, body in scenarios:
            with self.subTest(path=path):
                captured_kwargs: dict[str, object] = {}

                def _capture_request_mode_problem(**kwargs):
                    captured_kwargs.update(kwargs)
                    emit_payload = kwargs.get("on_payload_ready")
                    if callable(emit_payload):
                        emit_payload({"problemId": "streamed-problem", "title": "streamed"})
                    return {"problemId": "streamed-problem", "title": "streamed"}

                with patch("app.services.platform_public_bridge.request_mode_problem", side_effect=_capture_request_mode_problem):
                    response = self.client.post(
                        path,
                        json=body,
                        headers={"Accept": "text/event-stream"},
                    )

                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(captured_kwargs.get("defer_persistence"))
                self.assertTrue(callable(captured_kwargs.get("on_payload_ready")))
                self.assertTrue(callable(captured_kwargs.get("on_partial_ready")))
                self.assertIn("event: payload", response.text)

    def test_arrange_streaming_route_keeps_immediate_problem_request_contract(self) -> None:
        captured_kwargs: dict[str, object] = {}

        def _capture_request_mode_problem(**kwargs):
            captured_kwargs.update(kwargs)
            return {"problemId": "arrange-1", "title": "arrange"}

        with patch("app.services.platform_public_bridge.request_mode_problem", side_effect=_capture_request_mode_problem):
            response = self.client.post(
                "/platform/arrange/problem",
                json={"language": "python", "difficulty": "beginner"},
                headers={"Accept": "text/event-stream"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(captured_kwargs.get("defer_persistence"))
        self.assertIsNone(captured_kwargs.get("on_payload_ready"))
        self.assertIsNone(captured_kwargs.get("on_partial_ready"))


if __name__ == "__main__":
    unittest.main()
