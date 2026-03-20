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
        "goal": "Lock in the review loop for the next week.",
        "solutionSummary": "Use repeated review plus a short daily habit block.",
        "priorityActions": ["Replay three wrong answers", "Track solve time"],
        "phasePlan": ["Phase 1: review", "Phase 2: apply"],
        "dailyHabits": ["Solve two problems daily", "Spend 10 minutes reviewing"],
        "focusTopics": ["data structures", "search"],
        "metricsToTrack": ["accuracy", "average score"],
        "checkpoints": ["reach 70% weekly accuracy"],
        "riskMitigation": ["avoid rushing difficult prompts"],
        "metricSnapshot": {
            "attempts": 12,
            "accuracy": 66.7,
            "avgScore": 72.5,
            "trend": "recent trend is stable",
        },
        "reportBrief": {
            "title": "Lock in the review loop for the next week.",
            "summary": "Use repeated review plus a short daily habit block.",
        },
        "pdfDownloadUrl": f"/platform/reports/{report_id}/pdf" if report_id else None,
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

    def test_platform_report_returns_latest_stored_schema(self) -> None:
        payload = _new_report_payload(101)
        with patch.object(public_learning_route.platform_public_bridge, "get_public_report", return_value=payload):
            response = self.platform_client.get("/report")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), payload)

    def test_platform_report_returns_404_when_no_stored_report_exists(self) -> None:
        with patch.object(
            public_learning_route.platform_public_bridge,
            "get_public_report",
            side_effect=LookupError("report_not_found"),
        ):
            response = self.platform_client.get("/report")

        self.assertEqual(response.status_code, 404, response.text)

    def test_platform_milestone_returns_new_schema(self) -> None:
        payload = _new_report_payload(202)
        with patch.object(platform_reports_route, "create_milestone_report", return_value=payload):
            response = self.platform_client.post("/reports/milestone", json={"problem_count": 10})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), payload)

    def test_platform_report_pdf_download_returns_attachment(self) -> None:
        with patch.object(
            platform_reports_route,
            "generate_report_pdf_download",
            return_value=("learning-report-202.pdf", b"%PDF-1.4\nmock"),
        ):
            response = self.platform_client.get("/reports/202/pdf")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"%PDF-1.4\nmock")
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn('attachment; filename="learning-report-202.pdf"', response.headers["content-disposition"])

    def test_platform_report_pdf_download_returns_404_for_missing_report(self) -> None:
        with patch.object(
            platform_reports_route,
            "generate_report_pdf_download",
            side_effect=LookupError("report_not_found"),
        ):
            response = self.platform_client.get("/reports/999/pdf")

        self.assertEqual(response.status_code, 404, response.text)

    def test_platform_report_pdf_download_returns_503_when_pdf_generation_unavailable(self) -> None:
        with patch.object(
            platform_reports_route,
            "generate_report_pdf_download",
            side_effect=RuntimeError("report_pdf_generation_unavailable"),
        ):
            response = self.platform_client.get("/reports/999/pdf")

        self.assertEqual(response.status_code, 503, response.text)

    def test_platform_reports_latest_returns_recent_download_metadata(self) -> None:
        payload = {
            "available": True,
            "reportId": 303,
            "createdAt": "2026-03-19T12:00:00+00:00",
            "goal": "Latest report",
            "summary": "This is the most recent stored milestone report.",
            "pdfDownloadUrl": "/platform/reports/303/pdf",
        }
        with patch.object(
            platform_reports_route,
            "get_latest_report_download_metadata",
            return_value=payload,
        ):
            response = self.platform_client.get("/reports/latest")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), payload)

    def test_platform_reports_latest_returns_empty_payload_when_none_exists(self) -> None:
        payload = {
            "available": False,
            "reportId": None,
            "createdAt": None,
            "goal": "",
            "summary": "",
            "pdfDownloadUrl": None,
        }
        with patch.object(
            platform_reports_route,
            "get_latest_report_download_metadata",
            return_value=payload,
        ):
            response = self.platform_client.get("/reports/latest")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), payload)


if __name__ == "__main__":
    unittest.main()
