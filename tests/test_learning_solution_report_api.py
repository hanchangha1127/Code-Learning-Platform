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
import app.api.routes.public_learning as public_learning_route
import app.api.routes.reports as platform_reports_route
from server_runtime.webapp import app as root_app


def _new_report_payload(report_id: int | None) -> dict[str, object]:
    return {
        "reportId": report_id,
        "createdAt": "2026-03-05T10:00:00+00:00",
        "goal": "다음 주까지 오답 복기 루틴을 고정한다.",
        "solutionSummary": "짧은 복기와 일일 반복 학습으로 정확도와 점수를 함께 끌어올립니다.",
        "priorityActions": ["오답 3개 복기", "풀이 시간 기록"],
        "phasePlan": ["1단계: 기초 복기", "2단계: 실전 적용"],
        "dailyHabits": ["매일 2문제 풀이", "매일 10분 복기"],
        "focusTopics": ["자료구조", "탐색"],
        "metricsToTrack": ["정확도", "평균 점수"],
        "checkpoints": ["주말 정확도 70% 달성"],
        "riskMitigation": ["시간 압박 대응"],
        "metricSnapshot": {
            "attempts": 12,
            "accuracy": 66.7,
            "avgScore": 72.5,
            "trend": "최근 추세는 안정적입니다.",
        },
    }


class LearningSolutionReportApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root_client = TestClient(root_app)
        cls.platform_client = TestClient(platform_app)

    def setUp(self) -> None:
        platform_app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        platform_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1,
            username="solution-user",
            email="solution@example.com",
            role="user",
            status="active",
        )

    def tearDown(self) -> None:
        platform_app.dependency_overrides.clear()

    def test_api_report_returns_410_guidance(self) -> None:
        response = self.root_client.get("/api/report")
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(response.json().get("newPath"), "/platform/report")

    def test_platform_report_returns_new_schema(self) -> None:
        payload = _new_report_payload(101)
        with patch.object(public_learning_route.platform_public_bridge, "get_public_report", return_value=payload):
            response = self.platform_client.get("/report")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), payload)
        self.assertNotIn("summary", response.json())
        self.assertNotIn("recommendations", response.json())

    def test_platform_report_returns_503_on_ai_failure(self) -> None:
        with patch.object(
            public_learning_route.platform_public_bridge,
            "get_public_report",
            side_effect=RuntimeError("learning_report_generation_failed: generation_failed"),
        ):
            response = self.platform_client.get("/report")

        self.assertEqual(response.status_code, 503, response.text)

    def test_platform_milestone_returns_new_schema(self) -> None:
        payload = _new_report_payload(202)
        with patch.object(platform_reports_route, "create_milestone_report", return_value=payload):
            response = self.platform_client.post("/reports/milestone", json={"problem_count": 10})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), payload)


if __name__ == "__main__":
    unittest.main()
