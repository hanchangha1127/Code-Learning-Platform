import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from server.features.learning.api_submissions import analyze, get_analyses
from server.db.models import SubmissionStatus


class _SubmissionQuery:
    def __init__(self, submission):
        self._submission = submission

    def filter(self, *_args, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self._submission


class _AnalyzeDB:
    def __init__(self, submission):
        self.submission = submission
        self.commit_calls = 0
        self.rollback_calls = 0

    def query(self, _model):
        return _SubmissionQuery(self.submission)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def get(self, _model, key):
        if getattr(self.submission, "id", None) == key:
            return self.submission
        return None


class SubmissionApiTests(unittest.TestCase):
    def test_get_analyses_returns_404_when_submission_is_missing(self):
        with patch(
            "server.features.learning.api_submissions.list_analyses_for_submission",
            side_effect=ValueError("submission_not_found"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                get_analyses(
                    submission_id=999,
                    db=SimpleNamespace(),
                    current=SimpleNamespace(id=7),
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Submission not found")

    def test_analyze_allows_retry_after_error_status(self):
        submission = SimpleNamespace(
            id=11,
            user_id=7,
            status=SubmissionStatus.error,
            score=42,
            updated_at=None,
            created_at=None,
        )
        db = _AnalyzeDB(submission)

        with patch("server.features.learning.api_submissions.is_rq_enabled", return_value=False):
            response = analyze(
                submission_id=11,
                background_tasks=BackgroundTasks(),
                db=db,
                current=SimpleNamespace(id=7),
            )

        self.assertEqual(
            response,
            {"analysis_id": 11, "message": "Analysis started", "job_id": None},
        )
        self.assertEqual(submission.status, SubmissionStatus.processing)
        self.assertIsNone(submission.score)
        self.assertEqual(db.commit_calls, 1)


if __name__ == "__main__":
    unittest.main()

