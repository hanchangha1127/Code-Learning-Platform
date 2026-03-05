from __future__ import annotations

import os
import unittest
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.db.models import Problem, ProblemDifficulty, ProblemKind, Submission, UserProblemStat
from app.main import app as platform_backend_app
from server_runtime.webapp import app


class _FakeSession:
    def __init__(self, problem: Problem):
        self.problem = problem
        self.added: list[object] = []

    def get(self, model, key):
        if model is Problem:
            try:
                problem_id = int(key)
            except (TypeError, ValueError):
                return None
            if int(self.problem.id) == problem_id:
                return self.problem
            return None

        if model is UserProblemStat:
            if isinstance(key, dict):
                user_id = int(key.get("user_id"))
                problem_id = int(key.get("problem_id"))
            elif isinstance(key, tuple):
                user_id = int(key[0])
                problem_id = int(key[1])
            else:
                return None

            for item in self.added:
                if (
                    isinstance(item, UserProblemStat)
                    and int(item.user_id) == user_id
                    and int(item.problem_id) == problem_id
                ):
                    return item
            return None

        return None

    def add(self, item) -> None:
        if isinstance(item, Submission) and getattr(item, "id", None) is None:
            item.id = 1
            item.created_at = datetime.utcnow()
            item.updated_at = item.created_at
        self.added.append(item)

    def commit(self) -> None:
        return None

    def refresh(self, item) -> None:
        if isinstance(item, Submission) and getattr(item, "created_at", None) is None:
            item.created_at = datetime.utcnow()
            item.updated_at = item.created_at


def _build_problem(*, problem_id: int, is_published: bool, created_by: int | None) -> Problem:
    now = datetime.utcnow()
    problem = Problem(
        id=problem_id,
        kind=ProblemKind.coding,
        title="Problem",
        description="Read this problem.",
        difficulty=ProblemDifficulty.easy,
        language="python",
        starter_code="print('hello')",
        options=None,
        answer_index=None,
        reference_solution="print('hello')",
        is_published=is_published,
        created_by=created_by,
    )
    problem.created_at = now
    problem.updated_at = now
    return problem


class PlatformProblemAccessControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def tearDown(self) -> None:
        platform_backend_app.dependency_overrides.clear()

    def _override_platform_deps(self, *, db: _FakeSession, user_id: int = 1) -> None:
        platform_backend_app.dependency_overrides[get_db] = lambda: db
        platform_backend_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)

    def test_read_private_problem_blocks_other_users(self) -> None:
        db = _FakeSession(_build_problem(problem_id=9001, is_published=False, created_by=2))
        self._override_platform_deps(db=db, user_id=1)

        response = self.client.get("/platform/problems/9001")

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"detail": "Problem not found"})

    def test_read_private_problem_allows_owner(self) -> None:
        db = _FakeSession(_build_problem(problem_id=9002, is_published=False, created_by=1))
        self._override_platform_deps(db=db, user_id=1)

        response = self.client.get("/platform/problems/9002")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["id"], 9002)
        self.assertEqual(payload["is_published"], False)

    def test_submit_private_problem_blocks_other_users(self) -> None:
        db = _FakeSession(_build_problem(problem_id=9003, is_published=False, created_by=2))
        self._override_platform_deps(db=db, user_id=1)

        response = self.client.post(
            "/platform/problems/9003/submit",
            json={"language": "python", "code": "print(1)"},
        )

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"detail": "Problem not found"})
        submissions = [item for item in db.added if isinstance(item, Submission)]
        self.assertEqual(submissions, [])

    def test_submit_published_problem_allows_any_user(self) -> None:
        db = _FakeSession(_build_problem(problem_id=9004, is_published=True, created_by=2))
        self._override_platform_deps(db=db, user_id=1)

        response = self.client.post(
            "/platform/problems/9004/submit",
            json={"language": "python", "code": "print(1)"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["problem_id"], 9004)
        self.assertEqual(payload["user_id"], 1)
        self.assertEqual(payload["status"], "pending")


if __name__ == "__main__":
    unittest.main()
