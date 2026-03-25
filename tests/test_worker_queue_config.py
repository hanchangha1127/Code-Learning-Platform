from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app import worker


class WorkerQueueConfigTests(unittest.TestCase):
    def test_worker_uses_explicit_queue_override_when_configured(self) -> None:
        with patch.dict(os.environ, {"RQ_WORKER_QUEUES": "analysis, problem-follow-up, analysis"}, clear=False):
            queue_names = worker._worker_queue_names()

        self.assertEqual(queue_names, ["analysis", "problem-follow-up"])

    def test_worker_uses_enabled_queue_settings_by_default(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(worker.settings, "ANALYSIS_QUEUE_MODE", "rq"),
            patch.object(worker.settings, "ANALYSIS_QUEUE_NAME", "analysis"),
            patch.object(worker.settings, "PROBLEM_FOLLOW_UP_QUEUE_MODE", "rq"),
            patch.object(worker.settings, "PROBLEM_FOLLOW_UP_QUEUE_NAME", "problem-follow-up"),
        ):
            queue_names = worker._worker_queue_names()

        self.assertEqual(queue_names, ["problem-follow-up", "analysis"])


if __name__ == "__main__":
    unittest.main()
