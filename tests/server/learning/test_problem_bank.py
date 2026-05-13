from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from server.db.base import Base
from server.db.models import (
    Problem,
    ProblemContentStatus,
    ProblemDifficulty,
    ProblemKind,
    Submission,
    SubmissionStatus,
    UserProblemStat,
)
from server.features.learning import problem_bank_service


class _FakeStorage:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def append(self, record: dict) -> None:
        self.records.append(record)


class _FakeStorageManager:
    def __init__(self, storage: _FakeStorage) -> None:
        self.storage = storage

    def get_storage(self, _username: str) -> _FakeStorage:
        return self.storage

    def create_user_storage(self, _username: str) -> _FakeStorage:
        return self.storage


class ProblemBankServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()

    def _problem(
        self,
        problem_id: int,
        *,
        title: str = "Trace loop",
        published: bool = True,
        content_status: ProblemContentStatus = ProblemContentStatus.approved,
        answer_payload: dict | None = None,
        created_by: int | None = 1,
    ) -> Problem:
        problem = Problem(
            id=problem_id,
            external_id=f"analysis-{problem_id}",
            kind=ProblemKind.analysis,
            title=title,
            description="Explain the output.",
            difficulty=ProblemDifficulty.easy,
            language="python",
            starter_code="print(1)",
            problem_payload={
                "problemId": f"analysis-{problem_id}",
                "mode": "analysis",
                "title": title,
                "code": "print(1)",
                "prompt": "Explain the output.",
                "answer_index": 1,
                "explanation": "secret",
                "nested": {"reference_report": "secret"},
            },
            answer_payload=answer_payload if answer_payload is not None else {
                "type": "problem_instance",
                "problem_id": f"analysis-{problem_id}",
                "track": "code_reading",
                "language": "python",
                "code": "print(1)",
                "reference": "secret",
            },
            content_status=content_status,
            is_published=published,
            created_by=created_by,
        )
        self.db.add(problem)
        return problem

    def test_problem_bank_lists_only_public_replayable_visible_problems(self) -> None:
        self._problem(1, title="Visible problem")
        self._problem(2, title="Hidden problem", content_status=ProblemContentStatus.hidden)
        self._problem(3, title="Private problem", published=False, created_by=2)
        missing_replay = self._problem(4, title="Missing replay")
        missing_replay.answer_payload = None
        self.db.add_all(
            [
                Submission(id=1, user_id=7, problem_id=1, language="python", code="a", status=SubmissionStatus.passed, score=90),
                Submission(id=2, user_id=8, problem_id=1, language="python", code="b", status=SubmissionStatus.failed, score=20),
                UserProblemStat(user_id=7, problem_id=1, attempts=1, best_status=SubmissionStatus.passed, best_score=90),
            ]
        )
        self.db.commit()

        payload = problem_bank_service.list_problem_bank(self.db, user_id=7)

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["id"], 1)
        self.assertEqual(item["title"], "Visible problem")
        self.assertEqual(item["submissions"], 2)
        self.assertEqual(item["success_rate"], 50.0)
        self.assertEqual(item["my_status"], "solved")
        self.assertEqual(item["solve_link"], "/analysis.html?bank_problem=1")
        self.assertEqual(payload["summary"]["total_submissions"], 2)
        self.assertEqual(payload["summary"]["solved_count"], 1)

    def test_problem_bank_resume_sanitizes_answer_fields_and_injects_runtime_instance(self) -> None:
        self._problem(10, created_by=2)
        self.db.commit()
        storage = _FakeStorage()

        with patch.object(problem_bank_service, "storage_manager", _FakeStorageManager(storage)):
            payload = problem_bank_service.resume_problem_bank_item(
                self.db,
                user_id=7,
                username="solver",
                problem_id=10,
            )

        self.assertEqual(payload["problem"]["problemId"], "10")
        self.assertNotIn("answer_index", payload["problem"])
        self.assertNotIn("explanation", payload["problem"])
        self.assertNotIn("reference_report", payload["problem"]["nested"])
        self.assertEqual(storage.records[-1]["problem_id"], "10")
        self.assertEqual(storage.records[-1]["type"], "problem_instance")

    def test_problem_bank_resume_rejects_private_other_user_problem(self) -> None:
        self._problem(11, published=False, created_by=2)
        self.db.commit()

        with self.assertRaises(LookupError):
            problem_bank_service.resume_problem_bank_item(
                self.db,
                user_id=7,
                username="solver",
                problem_id=11,
            )

    def test_problem_bank_includes_historical_submitted_problem_even_if_not_marked_published(self) -> None:
        self._problem(12, title="Historical submitted problem", published=False, created_by=2)
        self.db.add(
            Submission(
                id=12,
                user_id=7,
                problem_id=12,
                language="python",
                code="print(1)",
                status=SubmissionStatus.failed,
                score=10,
            )
        )
        self.db.commit()

        payload = problem_bank_service.list_problem_bank(self.db, user_id=7)

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["id"], 12)
        self.assertEqual(payload["items"][0]["submissions"], 1)
        self.assertEqual(payload["summary"]["total_problems"], 1)

    def test_problem_bank_excludes_other_user_historical_submission_if_not_creator(self) -> None:
        self._problem(13, title="Other user historical submission", published=False, created_by=2)
        self.db.add(
            Submission(
                id=13,
                user_id=8,
                problem_id=13,
                language="python",
                code="print(1)",
                status=SubmissionStatus.failed,
                score=10,
            )
        )
        self.db.commit()

        payload = problem_bank_service.list_problem_bank(self.db, user_id=7)

        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["summary"]["total_problems"], 0)

    def test_problem_bank_resume_allows_historical_submitted_problem(self) -> None:
        self._problem(14, published=False, created_by=2)
        self.db.add(
            Submission(
                id=14,
                user_id=7,
                problem_id=14,
                language="python",
                code="print(1)",
                status=SubmissionStatus.failed,
                score=10,
            )
        )
        self.db.commit()
        storage = _FakeStorage()

        with patch.object(problem_bank_service, "storage_manager", _FakeStorageManager(storage)):
            payload = problem_bank_service.resume_problem_bank_item(
                self.db,
                user_id=7,
                username="solver",
                problem_id=14,
            )

        self.assertEqual(payload["bank_problem_id"], 14)
        self.assertEqual(storage.records[-1]["problem_id"], "14")

    def test_problem_bank_resume_rejects_private_problem_submitted_by_other_user(self) -> None:
        self._problem(15, published=False, created_by=2)
        self.db.add(
            Submission(
                id=15,
                user_id=8,
                problem_id=15,
                language="python",
                code="print(1)",
                status=SubmissionStatus.failed,
                score=10,
            )
        )
        self.db.commit()

        with self.assertRaises(LookupError):
            problem_bank_service.resume_problem_bank_item(
                self.db,
                user_id=7,
                username="solver",
                problem_id=15,
            )

    def test_problem_bank_paginates_visible_items_after_access_filter(self) -> None:
        self._problem(21, title="First visible")
        self._problem(22, title="Second visible")
        self._problem(23, title="Third visible")
        self._problem(24, title="Private other user", published=False, created_by=8)
        self.db.commit()

        payload = problem_bank_service.list_problem_bank(self.db, user_id=7, limit=1, offset=1)

        self.assertEqual(payload["total"], 3)
        self.assertEqual([item["id"] for item in payload["items"]], [22])
        self.assertEqual(payload["summary"]["total_problems"], 3)


if __name__ == "__main__":
    unittest.main()
