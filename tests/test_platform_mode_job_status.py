from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from rq.exceptions import NoSuchJobError

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.api.security_deps import get_current_user
from app.main import app


class _FakeJob:
    def __init__(self, *, status: str, args=(), result=None, exc_info: str = "", meta=None):
        self._status = status
        self.args = args
        self.result = result
        self.exc_info = exc_info
        self.meta = meta or {}

    def get_status(self, refresh: bool = False) -> str:  # noqa: ARG002
        return self._status


class PlatformModeJobStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_returns_finished_job_result_for_owner(self) -> None:
        fake_job = _FakeJob(
            status="finished",
            args=("auditor", 7, {"problem_id": "p1"}),
            result={"verdict": "passed", "score": 88},
            meta={"user_id": 7},
        )
        with (
            patch("app.api.routes.platform_mode_jobs.is_rq_enabled", return_value=True),
            patch("app.api.routes.platform_mode_jobs.get_redis_connection", return_value=object()),
            patch("app.api.routes.platform_mode_jobs.Job.fetch", return_value=fake_job),
        ):
            response = self.client.get("/mode-jobs/job-1")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {
                "jobId": "job-1",
                "status": "finished",
                "queued": False,
                "finished": True,
                "failed": False,
                "result": {"verdict": "passed", "score": 88},
                "error": None,
            },
        )

    def test_returns_404_when_job_owner_mismatch(self) -> None:
        fake_job = _FakeJob(status="started", args=("auditor", 3, {"problem_id": "p1"}), meta={"user_id": 3})
        with (
            patch("app.api.routes.platform_mode_jobs.is_rq_enabled", return_value=True),
            patch("app.api.routes.platform_mode_jobs.get_redis_connection", return_value=object()),
            patch("app.api.routes.platform_mode_jobs.Job.fetch", return_value=fake_job),
        ):
            response = self.client.get("/mode-jobs/job-2")

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"detail": "Job not found"})

    def test_returns_404_when_job_owner_is_missing(self) -> None:
        fake_job = _FakeJob(status="started", args=("auditor",), meta={})
        with (
            patch("app.api.routes.platform_mode_jobs.is_rq_enabled", return_value=True),
            patch("app.api.routes.platform_mode_jobs.get_redis_connection", return_value=object()),
            patch("app.api.routes.platform_mode_jobs.Job.fetch", return_value=fake_job),
        ):
            response = self.client.get("/mode-jobs/job-missing-owner")

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"detail": "Job not found"})

    def test_returns_404_for_missing_job(self) -> None:
        with (
            patch("app.api.routes.platform_mode_jobs.is_rq_enabled", return_value=True),
            patch("app.api.routes.platform_mode_jobs.get_redis_connection", return_value=object()),
            patch("app.api.routes.platform_mode_jobs.Job.fetch", side_effect=NoSuchJobError("job-404")),
        ):
            response = self.client.get("/mode-jobs/job-404")

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"detail": "Job not found"})

    def test_returns_400_when_queue_mode_is_not_rq(self) -> None:
        with patch("app.api.routes.platform_mode_jobs.is_rq_enabled", return_value=False):
            response = self.client.get("/mode-jobs/job-inline")

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(
            response.json(),
            {"detail": "Mode job status is available only when queue mode is rq"},
        )


if __name__ == "__main__":
    unittest.main()
