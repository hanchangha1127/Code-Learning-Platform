from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.db.models import AIAnalysis, AnalysisType, Problem, ProblemDifficulty, ProblemKind, Submission, SubmissionStatus, UserProblemStat
from app.services import report_service
from backend import learning_reporting


def _solution_plan() -> dict[str, object]:
    return {
        "goal": "Lower repeated wrong-answer frequency this week.",
        "solutionSummary": "Use a tighter review loop anchored on recent mistakes.",
        "priorityActions": ["Replay three wrong answers", "Write a short hint note"],
        "phasePlan": ["Week 1: review", "Week 2: apply"],
        "dailyHabits": ["Solve two problems daily"],
        "focusTopics": ["branching", "validation"],
        "metricsToTrack": ["accuracy", "logic_error frequency"],
        "checkpoints": ["reach 70% weekly accuracy"],
        "riskMitigation": ["review difficult prompts immediately"],
    }


class _FakeLegacyService:
    def __init__(self, history: list[dict[str, object]]) -> None:
        self._history = history
        self.captured: dict[str, object] | None = None
        self.ai_client = SimpleNamespace(generate_learning_solution_report=self._generate)

    def _generate(self, **kwargs):
        self.captured = kwargs
        return _solution_plan()

    def _get_user_storage(self, username: str) -> object:
        return object()

    def user_history(self, username: str) -> list[dict[str, object]]:
        return self._history

    def _get_problem_instance(self, storage: object, problem_id: object) -> dict[str, object]:
        return {}


class _FakeDB:
    def __init__(self, existing_reports: list[object] | None = None) -> None:
        self._existing_reports = list(existing_reports or [])
        self.added: list[object] = []
        self.deleted: list[object] = []
        self._next_id = 901

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", self._next_id)
                self._next_id += 1

    def commit(self) -> None:
        pass

    def delete(self, obj: object) -> None:
        self.deleted.append(obj)

    def query(self, model):
        db = self

        class _FakeQuery:
            def filter(self, *args, **kwargs):
                return self

            def all(self):
                rows = [*db._existing_reports, *db.added]
                return [row for row in rows if row not in db.deleted]

        return _FakeQuery()

    def refresh(self, obj: object) -> None:
        if getattr(obj, "id", None) is None:
            setattr(obj, "id", 901)
        if getattr(obj, "created_at", None) is None:
            setattr(obj, "created_at", datetime.now(timezone.utc))


class LearningSolutionReportDetailTests(unittest.TestCase):
    def test_legacy_learning_report_passes_per_problem_details(self) -> None:
        history = [
            {
                "mode": "code-block",
                "problem_title": "Fill the branch condition",
                "correct": False,
                "score": 30,
                "feedback": {
                    "summary": "The comparison operator was chosen incorrectly.",
                    "strengths": ["You understood the loop structure."],
                    "improvements": ["Recheck branch boundary values."],
                },
                "duration_seconds": 18,
                "problem_prompt": "Choose the branch condition that matches the loop.",
                "problem_code": "for i in range(3):\n    if ____:\n        print(i)",
                "problem_options": ["i < 3", "i <= 3"],
                "selected_option_text": "i <= 3",
                "correct_option_text": "i < 3",
                "selected_option": 1,
                "correct_answer_index": 0,
                "missed_types": ["branch boundary", "comparison operator"],
                "summary": "Branch selection exercise",
                "difficulty": "easy",
                "language": "python",
            }
        ]
        service = _FakeLegacyService(history)

        learning_reporting.learning_report(
            service,
            "detail-user",
            accuracy_from_events=lambda events: 0.0,
            duration_seconds=lambda created_at, solved_at: None,
        )

        self.assertIsNotNone(service.captured)
        detail_records = (service.captured or {}).get("detail_records")
        self.assertIsInstance(detail_records, list)
        record = detail_records[0]
        self.assertEqual(record["title"], "Fill the branch condition")
        self.assertEqual(record["expectedAnswer"], "i < 3")
        self.assertEqual(record["durationSeconds"], 18)
        self.assertTrue(record["evaluation"]["comparison"])
        metric_snapshot = (service.captured or {}).get("metric_snapshot")
        self.assertEqual(metric_snapshot["detailRecordCount"], 1)
        self.assertEqual(metric_snapshot["averageDurationSeconds"], 18.0)
        self.assertEqual(metric_snapshot["repeatedMissedPoints"][0]["label"], "branch boundary")

    def test_milestone_report_persists_strengths_and_download_metadata(self) -> None:
        now = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc)
        old_report = report_service.Report(
            id=700,
            user_id=1,
            report_type=report_service.ReportType.milestone,
            title="Old report",
            summary="Older saved report",
            stats={"source": "milestone_report"},
            created_at=now,
        )
        problem = Problem(
            id=21,
            external_id="prob-21",
            kind=ProblemKind.coding,
            title="Return array sum",
            description="Return the sum of the array.",
            difficulty=ProblemDifficulty.medium,
            language="python",
            starter_code="def solve(nums):\n    pass",
            problem_payload={"prompt": "Return the sum of the array."},
            answer_payload={},
        )
        submission = Submission(
            id=11,
            user_id=1,
            problem_id=21,
            language="python",
            code="def solve(nums):\n    return nums[0]",
            submission_payload={"bridgeId": "bridge-11", "durationSeconds": 74},
            status=SubmissionStatus.failed,
            score=40,
            created_at=now,
        )
        submission.problem = problem
        analysis = AIAnalysis(
            id=31,
            user_id=1,
            submission_id=11,
            analysis_type=AnalysisType.review,
            result_summary="logic_error",
            result_detail="expected sum of all values but returned only first item",
            result_payload={
                "feedback": {
                    "summary": "The accumulation logic is missing.",
                    "strengths": ["The function signature is correct."],
                    "improvements": ["Use a running total or sum()."],
                },
                "foundTypes": ["function_signature"],
                "missedTypes": ["accumulation_logic", "edge_case"],
            },
            created_at=now,
        )
        stats_by_problem = {
            21: UserProblemStat(
                user_id=1,
                problem_id=21,
                attempts=2,
                wrong_answer_types={
                    "total_wrong": 2,
                    "types": {"logic_error": 2},
                    "last_wrong_type": "logic_error",
                    "last_wrong_at": now.isoformat(),
                },
                last_submitted_at=now,
            )
        }

        fake_db = _FakeDB(existing_reports=[old_report])
        captured: dict[str, object] = {}

        def _capture_generate(**kwargs):
            captured.update(kwargs)
            return _solution_plan()

        with patch.object(report_service, "_load_recent_submissions", return_value=[submission]), patch.object(
            report_service, "_load_recent_analyses", return_value=[analysis]
        ), patch.object(report_service, "_load_problem_stats_map", return_value=stats_by_problem), patch.object(
            report_service._learning_report_ai,
            "generate_learning_solution_report",
            side_effect=_capture_generate,
        ):
            result = report_service.create_milestone_report(fake_db, user_id=1, problem_count=10)

        self.assertEqual(result["reportId"], 901)
        self.assertIn("reportBrief", result)
        self.assertEqual(result["pdfDownloadUrl"], "/platform/reports/901/pdf")
        detail_records = captured.get("detail_records")
        self.assertIsInstance(detail_records, list)
        self.assertEqual(detail_records[0]["evaluation"]["wrongType"], "logic_error")
        self.assertEqual(detail_records[0]["durationSeconds"], 74)
        self.assertEqual(detail_records[0]["attemptsOnProblem"], 2)
        metric_snapshot = captured.get("metric_snapshot")
        self.assertEqual(metric_snapshot["detailRecordCount"], 1)
        self.assertEqual(metric_snapshot["topWrongTypes"][0]["type"], "logic_error")
        self.assertEqual(metric_snapshot["repeatedWrongTypes"][0]["label"], "logic_error")
        stored_report = fake_db.added[-1]
        self.assertTrue(stored_report.strengths)
        self.assertTrue(stored_report.weaknesses)
        self.assertIn("learningEvidence", stored_report.stats)
        self.assertEqual([item.id for item in fake_db.deleted], [700])

    def test_milestone_report_detail_records_keep_advanced_analysis_mode(self) -> None:
        now = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc)
        problem = Problem(
            id=22,
            external_id="sfile:22",
            kind=ProblemKind.analysis,
            title="Review a single file",
            description="Inspect the service layer.",
            difficulty=ProblemDifficulty.medium,
            language="python",
            starter_code="def handler():\n    return None",
            problem_payload={
                "workspace": "single-file-analysis.workspace",
                "files": [{"path": "app/service.py", "content": "def handler():\n    return None"}],
            },
            answer_payload={},
        )
        submission = Submission(
            id=12,
            user_id=1,
            problem_id=22,
            language="python",
            code="analysis report body",
            submission_payload={"report": "analysis report body"},
            status=SubmissionStatus.failed,
            score=55,
            created_at=now,
        )
        submission.problem = problem
        analysis = AIAnalysis(
            id=32,
            user_id=1,
            submission_id=12,
            analysis_type=AnalysisType.review,
            result_summary="analysis_error",
            result_detail="missed service edge case",
            result_payload={"feedback": {"summary": "Need deeper file-level reasoning."}},
            created_at=now,
        )

        detail_records = report_service._build_learning_detail_records(
            [submission],
            analyses_by_submission={12: analysis},
            stats_by_problem={},
        )

        self.assertEqual(detail_records[0]["mode"], "single-file-analysis")
        self.assertTrue(detail_records[0]["modeLabel"])


if __name__ == "__main__":
    unittest.main()
