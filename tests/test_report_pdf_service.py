from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.db.models import Report, ReportType
from app.services.report_pdf_service import (
    _LATEST_REPORT_BATCH_SIZE,
    build_report_brief,
    build_report_pdf_bytes,
    build_report_pdf_download_url,
    get_latest_report_detail,
    get_latest_report_download_metadata,
)


class _FakeQuery:
    def __init__(self, reports):
        self._reports = list(reports)
        self._limit = None
        self._offset = 0
        self.all_calls: list[tuple[int, int | None]] = []

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def offset(self, value):
        self._offset = value
        return self

    def first(self):
        rows = self.all()
        return rows[0] if rows else None

    def all(self):
        self.all_calls.append((self._offset, self._limit))
        start = max(int(self._offset or 0), 0)
        if self._limit is None:
            return list(self._reports[start:])
        stop = start + max(int(self._limit), 0)
        return list(self._reports[start:stop])


class _FakeDB:
    def __init__(self, reports):
        self._reports = list(reports)
        self.last_query: _FakeQuery | None = None

    def query(self, model):
        self.last_query = _FakeQuery(self._reports)
        return self.last_query


class ReportPdfServiceTests(unittest.TestCase):
    def test_build_report_brief_returns_compact_sections(self) -> None:
        brief = build_report_brief(
            solution_plan={
                "goal": "Reduce logic mistakes this week",
                "solutionSummary": "Add counterexample checks before submission.",
                "priorityActions": [
                    "Review three wrong answers",
                    "Write three counterexamples",
                    "Use a pre-submit checklist",
                    "duplicate",
                ],
                "dailyHabits": ["Review two problems daily", "Run a short timed set"],
                "checkpoints": ["reach 70 percent accuracy", "reduce logic_error share"],
            },
            metric_snapshot={
                "attempts": 12,
                "accuracy": 66.7,
                "avgScore": 72.5,
                "trend": "stable",
            },
            fallback_title="Learning report",
            fallback_summary="",
        )

        self.assertEqual(brief["title"], "Reduce logic mistakes this week")
        self.assertLessEqual(len(brief["focusActions"]), 3)
        self.assertLessEqual(len(brief["nextSteps"]), 3)
        self.assertTrue(str(brief["metrics"][0]["value"]).startswith("12"))

    def test_build_report_pdf_download_url_formats_platform_path(self) -> None:
        self.assertEqual(build_report_pdf_download_url(31), "/platform/reports/31/pdf")
        self.assertIsNone(build_report_pdf_download_url(None))

    def test_get_latest_report_download_metadata_returns_empty_payload_when_missing(self) -> None:
        payload = get_latest_report_download_metadata(_FakeDB([]), user_id=7)

        self.assertEqual(payload["available"], False)
        self.assertIsNone(payload["reportId"])
        self.assertIsNone(payload["pdfDownloadUrl"])

    def test_get_latest_report_download_metadata_skips_legacy_bridge_report(self) -> None:
        legacy_report = Report(
            id=40,
            user_id=7,
            report_type=ReportType.milestone,
            title="legacy",
            summary="legacy summary",
            stats={"source": "platform"},
            created_at=datetime(2026, 3, 20, 10, 30, tzinfo=timezone.utc),
        )
        latest_valid_report = Report(
            id=41,
            user_id=7,
            report_type=ReportType.milestone,
            title="Latest report",
            summary="Stored milestone summary.",
            stats={
                "source": "milestone_report",
                "reportBrief": {
                    "title": "Latest report",
                    "summary": "Stored milestone summary.",
                },
            },
            created_at=datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc),
        )

        payload = get_latest_report_download_metadata(_FakeDB([legacy_report, latest_valid_report]), user_id=7)

        self.assertEqual(payload["available"], True)
        self.assertEqual(payload["reportId"], 41)
        self.assertEqual(payload["goal"], "Latest report")
        self.assertEqual(payload["pdfDownloadUrl"], "/platform/reports/41/pdf")

    def test_get_latest_report_detail_returns_full_saved_payload(self) -> None:
        report = Report(
            id=51,
            user_id=7,
            report_type=ReportType.milestone,
            title="Stored title",
            summary="Stored summary",
            recommendations=["Review three wrong answers"],
            stats={
                "source": "milestone_report",
                "solutionPlan": {
                    "goal": "Stored goal",
                    "solutionSummary": "Stored detail summary",
                    "priorityActions": ["Review three wrong answers"],
                    "phasePlan": ["Phase 1"],
                    "dailyHabits": ["Review daily"],
                    "focusTopics": ["data structures"],
                    "metricsToTrack": ["accuracy"],
                    "checkpoints": ["reach 70 percent accuracy"],
                    "riskMitigation": ["review first when time is short"],
                },
                "metricSnapshot": {
                    "attempts": 12,
                    "accuracy": 66.7,
                    "avgScore": 72.5,
                    "trend": "stable",
                },
                "reportBrief": {
                    "title": "Stored goal",
                    "summary": "Stored detail summary",
                },
            },
            created_at=datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc),
        )

        payload = get_latest_report_detail(_FakeDB([report]), user_id=7)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["reportId"], 51)
        self.assertEqual(payload["goal"], "Stored goal")
        self.assertEqual(payload["reportBrief"]["title"], "Stored goal")
        self.assertEqual(payload["pdfDownloadUrl"], "/platform/reports/51/pdf")

    def test_get_latest_report_download_metadata_queries_milestones_in_batches(self) -> None:
        legacy_reports = [
            Report(
                id=100 + index,
                user_id=7,
                report_type=ReportType.milestone,
                title=f"legacy-{index}",
                summary="legacy summary",
                stats={"source": "platform"},
                created_at=datetime(2026, 3, 20, 10, 30, tzinfo=timezone.utc),
            )
            for index in range(_LATEST_REPORT_BATCH_SIZE)
        ]
        valid_report = Report(
            id=999,
            user_id=7,
            report_type=ReportType.milestone,
            title="Valid report",
            summary="Stored milestone summary.",
            stats={
                "source": "milestone_report",
                "reportBrief": {
                    "title": "Valid report",
                    "summary": "Stored milestone summary.",
                },
            },
            created_at=datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc),
        )
        fake_db = _FakeDB([*legacy_reports, valid_report])

        payload = get_latest_report_download_metadata(fake_db, user_id=7)

        self.assertEqual(payload["reportId"], 999)
        self.assertEqual(
            fake_db.last_query.all_calls,
            [(0, _LATEST_REPORT_BATCH_SIZE), (_LATEST_REPORT_BATCH_SIZE, _LATEST_REPORT_BATCH_SIZE)],
        )

    def test_build_report_pdf_bytes_returns_pdf_document(self) -> None:
        report = Report(
            id=31,
            user_id=1,
            report_type=ReportType.milestone,
            title="Reduce logic mistakes this week",
            summary="Add a fixed counterexample review routine.",
            recommendations=["Review three wrong answers"],
            stats={
                "solutionPlan": {
                    "goal": "Reduce logic mistakes this week",
                    "solutionSummary": "Add counterexample checks before submission.",
                    "priorityActions": ["Review three wrong answers", "Write three counterexamples"],
                    "dailyHabits": ["Review two problems daily"],
                    "checkpoints": ["reach 70 percent accuracy"],
                },
                "metricSnapshot": {
                    "attempts": 12,
                    "accuracy": 66.7,
                    "avgScore": 72.5,
                    "trend": "stable",
                },
            },
            created_at=datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc),
        )

        pdf_bytes = build_report_pdf_bytes(report)

        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_build_report_pdf_bytes_renders_richer_plan_and_evidence_sections(self) -> None:
        minimal_report = Report(
            id=32,
            user_id=1,
            report_type=ReportType.milestone,
            title="Learning report",
            summary="Short summary",
            stats={
                "solutionPlan": {
                    "goal": "Learning report",
                    "solutionSummary": "Short summary",
                    "priorityActions": ["Review the latest mistake"],
                },
                "metricSnapshot": {
                    "attempts": 4,
                    "accuracy": 50,
                    "avgScore": 60,
                    "trend": "stable",
                },
            },
            created_at=datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc),
        )
        rich_report = Report(
            id=33,
            user_id=1,
            report_type=ReportType.milestone,
            title="Learning report",
            summary="Short summary",
            recommendations=["Review the latest mistake"],
            stats={
                "source": "milestone_report",
                "solutionPlan": {
                    "goal": "Learning report",
                    "solutionSummary": "Short summary",
                    "priorityActions": [
                        "Review the latest mistake",
                        "Write one counterexample",
                        "Summarize the key error pattern",
                    ],
                    "phasePlan": [
                        "Phase 1: review the latest failure",
                        "Phase 2: redo with a new constraint",
                    ],
                    "dailyHabits": [
                        "Spend 10 minutes on one weak area",
                        "Keep a short correction log",
                    ],
                    "focusTopics": [
                        "logic",
                        "boundary conditions",
                        "time management",
                    ],
                    "metricsToTrack": [
                        "accuracy",
                        "average score",
                        "wrong type share",
                    ],
                    "checkpoints": [
                        "reach 70 percent accuracy",
                        "reduce repeated mistakes",
                    ],
                    "riskMitigation": [
                        "slow down on first read",
                        "recheck the final answer",
                    ],
                },
                "metricSnapshot": {
                    "attempts": 12,
                    "accuracy": 66.7,
                    "avgScore": 72.5,
                    "trend": "stable",
                },
                "detailRecords": [
                    {
                        "title": "Array traversal review",
                        "modeLabel": "코드 배치",
                        "result": "wrong",
                        "score": 45,
                        "durationSeconds": 82,
                        "difficulty": "medium",
                        "language": "python",
                        "learnerResponse": "Moved the loop one step too early.",
                        "expectedAnswer": "Advance only after validating the current index.",
                        "questionContext": {
                            "prompt": "Place the algorithm steps in the correct order.",
                            "scenario": "Boundary checks were skipped in the first attempt.",
                            "codeOrContext": "for idx in range(len(items)):",
                        },
                        "evaluation": {
                            "feedbackSummary": "You started the loop too early and missed the guard condition.",
                            "strengths": ["Kept the loop structure readable"],
                            "improvements": ["Check the condition before advancing"],
                            "missedPoints": ["Guard clause", "index boundary"],
                            "matchedPoints": ["loop structure"],
                            "comparison": "The reference answer checks the guard first.",
                            "referenceExplanation": "Move the validation step before the iteration.",
                        },
                    },
                    {
                        "title": "Sorting rule selection",
                        "modeLabel": "알고리즘",
                        "result": "correct",
                        "score": 88,
                        "durationSeconds": 63,
                        "difficulty": "hard",
                        "language": "python",
                        "learnerResponse": "Selected the stable method after comparing alternatives.",
                        "expectedAnswer": "Choose the stable algorithm for the given constraint.",
                        "questionContext": {
                            "prompt": "Pick the best algorithm for the scenario.",
                            "scenario": "The data must preserve order for equal elements.",
                        },
                        "evaluation": {
                            "feedbackSummary": "Good selection and good reasoning.",
                            "strengths": ["Compared tradeoffs before answering"],
                            "improvements": ["Add one sentence on why the alternative is slower"],
                            "matchedPoints": ["stability requirement", "tradeoff comparison"],
                        },
                    },
                ],
            },
            created_at=datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc),
        )

        minimal_pdf = build_report_pdf_bytes(minimal_report)
        rich_pdf = build_report_pdf_bytes(rich_report)

        self.assertTrue(rich_pdf.startswith(b"%PDF-"))
        self.assertGreater(len(minimal_pdf), 1000)
        self.assertGreater(len(rich_pdf), len(minimal_pdf) + 800)
        self.assertGreater(len(rich_pdf), 2500)


if __name__ == "__main__":
    unittest.main()
