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

from server.dependencies import get_db
from server.features.auth.dependencies import get_current_user
from server.app import platform_app as platform_backend_app
from server.app import app


class LearningContinuityApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        platform_backend_app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        platform_backend_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=44,
            username="continuity-user",
            email="continuity@example.com",
            role="user",
            status="active",
        )

    def tearDown(self) -> None:
        platform_backend_app.dependency_overrides.clear()

    def test_platform_home_returns_learning_home_payload(self) -> None:
        expected = {
            "displayName": "Tester",
            "todayDate": "2026-03-06",
            "streakDays": 3,
            "skillLevel": "level1",
            "dailyGoal": {
                "date": "2026-03-06",
                "targetSessions": 12,
                "completedSessions": 5,
                "remainingSessions": 7,
                "progressPercent": 41.7,
                "achieved": False,
            },
            "reviewQueue": {
                "dueCount": 1,
                "items": [
                    {
                        "id": 7,
                        "mode": "analysis",
                        "modeLabel": "코드 분석",
                        "title": "Trace loop",
                        "weaknessTag": "logic_error",
                        "weaknessLabel": "로직 오류",
                        "dueAt": "2026-03-06T09:00:00",
                        "priority": 80,
                        "actionLink": "/analysis.html",
                        "resumeLink": "/analysis.html?resume_review=7",
                        "sourceProblemId": "an-7",
                    }
                ],
            },
            "todayTasks": [],
            "weakTopics": ["로직 오류"],
            "recommendedModes": [{"mode": "analysis", "label": "코드 분석", "link": "/analysis.html"}],
            "trend": {
                "last7DaysAttempts": 5,
                "last30DaysAttempts": 14,
                "last7DaysAccuracy": 60.0,
                "last30DaysAccuracy": 71.4,
            },
            "stats": {"totalAttempts": 14, "accuracy": 71.4},
            "focusModes": ["analysis"],
            "focusTopics": ["로직 오류"],
            "weeklyReportCard": {
                "available": True,
                "reportId": 9,
                "createdAt": "2026-03-06T08:00:00",
                "goal": "이번 주 복습 리듬 고정",
                "solutionSummary": "오답 복습과 일일 학습 루틴을 우선하세요.",
                "actionLink": "/profile.html",
                "stale": False,
            },
            "notifications": [
                {
                    "type": "review_queue",
                    "severity": "warn",
                    "title": "복습할 문제가 남아 있습니다.",
                    "description": "대기 중인 복습 1건을 처리해 약점을 바로 보강해 보세요.",
                    "actionLabel": "복습 시작",
                    "actionLink": "/analysis.html?resume_review=7",
                    "count": 1,
                }
            ],
        }
        with (
            patch("server.features.learning.api_public_learning.learning_service.get_public_history", return_value=[]) as mock_history,
            patch("server.features.learning.api_public_learning.learning_service.get_public_profile", return_value={"skillLevel": "level1"}) as mock_profile,
            patch("server.features.learning.api_public_learning.learning_service.get_public_me", return_value={"displayName": "Tester"}),
            patch("server.features.learning.api_public_learning.build_learning_home", return_value=expected),
        ):
            response = self.client.get("/platform/home")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), expected)
        mock_history.assert_called_once_with("continuity-user", limit=200)
        mock_profile.assert_called_once_with("continuity-user")

    def test_platform_learning_history_returns_metadata_payload(self) -> None:
        expected = {
            "history": [{"problem_id": "an-1"}],
            "total": 3,
            "hasMore": True,
            "limit": 25,
        }
        with patch(
            "server.features.learning.api_public_learning.learning_service.get_public_history_page",
            return_value=expected,
        ) as mock_history_page:
            response = self.client.get("/platform/learning/history?limit=25")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), expected)
        mock_history_page.assert_called_once_with("continuity-user", limit=25)

    def test_platform_review_queue_returns_due_items(self) -> None:
        payload = [{
            "id": 1,
            "mode": "analysis",
            "modeLabel": "코드 분석",
            "title": "반복문 추적",
            "weaknessTag": "logic_error",
            "weaknessLabel": "로직 오류",
            "dueAt": "2026-03-06T09:00:00",
            "priority": 80,
            "actionLink": "/analysis.html",
            "resumeLink": "/analysis.html?resume_review=1",
            "sourceProblemId": "an-1",
        }]
        with patch("server.features.learning.api_public_learning.list_due_review_queue", return_value=payload):
            response = self.client.get("/platform/learning/review-queue")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["dueCount"], 1)
        self.assertEqual(response.json()["items"], payload)

    def test_platform_review_resume_returns_problem_payload(self) -> None:
        payload = {
            "reviewItemId": 3,
            "mode": "analysis",
            "resumeLink": "/analysis.html?resume_review=3",
            "problem": {
                "problemId": "an-3",
                "title": "Resume problem",
                "language": "python",
            },
        }
        with patch("server.features.learning.api_public_learning.resume_review_queue_item", return_value=payload):
            response = self.client.get("/platform/review-queue/3/resume")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), payload)

    def test_platform_review_resume_returns_404_when_missing(self) -> None:
        with patch("server.features.learning.api_public_learning.resume_review_queue_item", side_effect=LookupError("missing")):
            response = self.client.get("/platform/review-queue/999/resume")

        self.assertEqual(response.status_code, 404, response.text)

    def test_me_goal_get_returns_serialized_goal(self) -> None:
        serialized = {
            "dailyTargetSessions": 12,
            "focusModes": ["analysis"],
            "focusTopics": ["로직 오류"],
            "updatedAt": "2026-03-06T12:00:00",
        }
        with (
            patch("server.features.account.api.get_or_create_learning_goal", return_value=SimpleNamespace()),
            patch("server.features.account.api.serialize_learning_goal", return_value=serialized),
        ):
            response = self.client.get("/platform/me/goal")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), serialized)

    def test_me_goal_put_updates_goal(self) -> None:
        serialized = {
            "dailyTargetSessions": 20,
            "focusModes": ["analysis", "code-arrange"],
            "focusTopics": ["로직 오류", "문법 오류"],
            "updatedAt": "2026-03-06T12:30:00",
        }
        with (
            patch("server.features.account.api.update_learning_goal", return_value=SimpleNamespace()) as mock_update,
            patch("server.features.account.api.serialize_learning_goal", return_value=serialized),
        ):
            response = self.client.put(
                "/platform/me/goal",
                json={
                    "daily_target_sessions": 20,
                    "focus_modes": ["analysis", "code-arrange"],
                    "focus_topics": ["로직 오류", "문법 오류"],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), serialized)
        mock_update.assert_called_once()


if __name__ == "__main__":
    unittest.main()

