from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.main import app
from app.services.analysis_queue import QueueEnqueueResult


class PlatformModeQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_submit_routes_use_shared_queue_path_when_rq_enabled(self) -> None:
        scenarios = [
            {
                "path": "/auditor/submit",
                "mode": "auditor",
                "request_payload": {"problemId": "aud-1", "report": "report body"},
                "queue_payload": {"problem_id": "aud-1", "report": "report body"},
            },
            {
                "path": "/context-inference/submit",
                "mode": "context-inference",
                "request_payload": {"problemId": "ctx-1", "report": "report body"},
                "queue_payload": {"problem_id": "ctx-1", "report": "report body"},
            },
            {
                "path": "/refactoring-choice/submit",
                "mode": "refactoring-choice",
                "request_payload": {"problemId": "ref-1", "selectedOption": "A", "report": "report body"},
                "queue_payload": {"problem_id": "ref-1", "selected_option": "A", "report": "report body"},
            },
            {
                "path": "/code-blame/submit",
                "mode": "code-blame",
                "request_payload": {"problemId": "blame-1", "selectedCommits": ["A"], "report": "report body"},
                "queue_payload": {"problem_id": "blame-1", "selected_commits": ["A"], "report": "report body"},
            },
        ]

        for scenario in scenarios:
            with self.subTest(path=scenario["path"]):
                with (
                    patch("app.api.routes.platform_mode_queue.is_rq_enabled", return_value=True),
                    patch(
                        "app.api.routes.platform_mode_queue.enqueue_platform_mode_submit_job",
                        return_value=QueueEnqueueResult(job_id="job-123", queue_name="analysis"),
                    ) as mock_enqueue,
                    patch("app.api.routes.platform_mode_queue.record_platform_mode_submit_dispatch") as mock_dispatch,
                    patch("app.api.routes.platform_mode_queue.record_platform_mode_enqueue_failure") as mock_enqueue_failure,
                ):
                    response = self.client.post(scenario["path"], json=scenario["request_payload"])

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    response.json(),
                    {
                        "queued": True,
                        "message": "Submission queued",
                        "jobId": "job-123",
                    },
                )
                mock_enqueue.assert_called_once()
                _, enqueue_kwargs = mock_enqueue.call_args
                self.assertEqual(enqueue_kwargs["mode"], scenario["mode"])
                self.assertEqual(enqueue_kwargs["user_id"], 1)
                self.assertEqual(enqueue_kwargs["payload"]["request_id"] != "", True)
                self.assertEqual(
                    {k: v for k, v in enqueue_kwargs["payload"].items() if k != "request_id"},
                    scenario["queue_payload"],
                )
                self.assertEqual(enqueue_kwargs["request_id"], enqueue_kwargs["payload"]["request_id"])
                mock_dispatch.assert_called_once_with(
                    mode=scenario["mode"],
                    user_id=1,
                    queued=True,
                    job_id="job-123",
                    queue_name="analysis",
                )
                mock_enqueue_failure.assert_not_called()

    def test_submit_routes_record_inline_dispatch_when_rq_disabled(self) -> None:
        scenarios = [
            {
                "path": "/auditor/submit",
                "mode": "auditor",
                "request_payload": {"problemId": "aud-1", "report": "report body"},
                "service_patch": "app.api.routes.auditor.submit_auditor_report",
                "service_response": {
                    "correct": True,
                    "score": 81.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "reference",
                    "passThreshold": 70,
                },
            },
            {
                "path": "/context-inference/submit",
                "mode": "context-inference",
                "request_payload": {"problemId": "ctx-1", "report": "report body"},
                "service_patch": "app.api.routes.context_inference.submit_context_inference_report",
                "service_response": {
                    "correct": True,
                    "score": 81.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "reference",
                    "passThreshold": 70,
                },
            },
            {
                "path": "/refactoring-choice/submit",
                "mode": "refactoring-choice",
                "request_payload": {"problemId": "ref-1", "selectedOption": "A", "report": "report body"},
                "service_patch": "app.api.routes.refactoring_choice.submit_refactoring_choice_report",
                "service_response": {
                    "correct": True,
                    "score": 81.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "reference",
                    "passThreshold": 70,
                    "selectedOption": "A",
                    "bestOption": "A",
                    "optionReviews": [
                        {"optionId": "A", "summary": "best"},
                        {"optionId": "B", "summary": "alt"},
                        {"optionId": "C", "summary": "alt"},
                    ],
                },
            },
            {
                "path": "/code-blame/submit",
                "mode": "code-blame",
                "request_payload": {"problemId": "blame-1", "selectedCommits": ["A"], "report": "report body"},
                "service_patch": "app.api.routes.code_blame.submit_code_blame_report",
                "service_response": {
                    "correct": True,
                    "score": 81.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "reference",
                    "passThreshold": 70,
                    "selectedCommits": ["A"],
                    "culpritCommits": ["A"],
                    "commitReviews": [
                        {"optionId": "A", "summary": "root cause"},
                        {"optionId": "B", "summary": "noise"},
                        {"optionId": "C", "summary": "noise"},
                        {"optionId": "D", "summary": "noise"},
                        {"optionId": "E", "summary": "noise"},
                    ],
                },
            },
        ]

        for scenario in scenarios:
            with self.subTest(path=scenario["path"]):
                with (
                    patch("app.api.routes.platform_mode_queue.is_rq_enabled", return_value=False),
                    patch(scenario["service_patch"], return_value=scenario["service_response"]) as mock_service,
                    patch("app.api.routes.platform_mode_queue.record_platform_mode_submit_dispatch") as mock_dispatch,
                    patch("app.api.routes.platform_mode_queue.record_platform_mode_enqueue_failure") as mock_enqueue_failure,
                ):
                    response = self.client.post(scenario["path"], json=scenario["request_payload"])

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), scenario["service_response"])
                mock_service.assert_called_once()
                mock_dispatch.assert_called_once_with(
                    mode=scenario["mode"],
                    user_id=1,
                    queued=False,
                )
                mock_enqueue_failure.assert_not_called()

    def test_submit_routes_record_enqueue_failure_when_rq_enqueue_fails(self) -> None:
        with (
            patch("app.api.routes.platform_mode_queue.is_rq_enabled", return_value=True),
            patch(
                "app.api.routes.platform_mode_queue.enqueue_platform_mode_submit_job",
                side_effect=RuntimeError("enqueue failed"),
            ),
            patch("app.api.routes.platform_mode_queue.record_platform_mode_submit_dispatch") as mock_dispatch,
            patch("app.api.routes.platform_mode_queue.record_platform_mode_enqueue_failure") as mock_enqueue_failure,
        ):
            response = self.client.post(
                "/auditor/submit",
                json={"problemId": "aud-1", "report": "report body"},
            )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json(), {"detail": "Failed to enqueue mode submission job"})
        mock_dispatch.assert_not_called()
        mock_enqueue_failure.assert_called_once_with(
            mode="auditor",
            user_id=1,
            error=ANY,
        )


if __name__ == "__main__":
    unittest.main()
