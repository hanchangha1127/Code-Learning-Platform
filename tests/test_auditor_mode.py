from __future__ import annotations

import unittest
from unittest.mock import patch

from app.db.models import (
    AIAnalysis,
    Problem,
    ProblemDifficulty,
    ProblemKind,
    Submission,
)
from app.services.auditor_service import create_auditor_problem, map_auditor_difficulty, submit_auditor_report
from backend.learning_mode_handlers import AUDITOR_TRAP_COUNT_BY_DIFFICULTY
from server_runtime.schemas import AuditorSubmitRequest


class AuditorSchemaTests(unittest.TestCase):
    def test_auditor_submit_request_accepts_aliases(self):
        first = AuditorSubmitRequest(problemId="p1", report="리포트")
        second = AuditorSubmitRequest(problem_id="p2", report="리포트")

        self.assertEqual(first.problem_id, "p1")
        self.assertEqual(second.problem_id, "p2")

    def test_auditor_submit_request_strips_report_whitespace(self):
        item = AuditorSubmitRequest(problemId="p1", report="  리포트  ")
        self.assertEqual(item.report, "리포트")


class AuditorMappingTests(unittest.TestCase):
    def test_trap_count_mapping(self):
        self.assertEqual(AUDITOR_TRAP_COUNT_BY_DIFFICULTY["beginner"], 1)
        self.assertEqual(AUDITOR_TRAP_COUNT_BY_DIFFICULTY["intermediate"], 2)
        self.assertEqual(AUDITOR_TRAP_COUNT_BY_DIFFICULTY["advanced"], 3)

    def test_platform_difficulty_mapping(self):
        self.assertEqual(map_auditor_difficulty("beginner"), ProblemDifficulty.easy)
        self.assertEqual(map_auditor_difficulty("intermediate"), ProblemDifficulty.medium)
        self.assertEqual(map_auditor_difficulty("advanced"), ProblemDifficulty.hard)
        with self.assertRaises(ValueError):
            map_auditor_difficulty("expert")


class AuditorSqlSubmitTests(unittest.TestCase):
    def setUp(self) -> None:
        problem = Problem(
            id=101,
            kind=ProblemKind.auditor,
            title="감사 테스트",
            description="코드 함정을 찾으세요.",
            difficulty=ProblemDifficulty.easy,
            language="python",
            starter_code="print('hello')",
            options={
                "trap_catalog": [
                    {"type": "logic_error", "description": "경계값 오류"},
                    {"type": "injection_risk", "description": "문자열 결합"},
                ],
                "reference_report": "모범 리포트",
                "client_difficulty": "beginner",
            },
            reference_solution="모범 리포트",
            is_published=False,
            created_by=1,
        )

        class _FakeSession:
            def __init__(self, problem_obj):
                self._problem = problem_obj
                self.added = []
                self.committed = False

            def get(self, model, key):
                if model is Problem and int(key) == int(self._problem.id):
                    return self._problem
                return None

            def add(self, item):
                # emulate auto id assignment after flush
                if isinstance(item, Submission) and getattr(item, "id", None) is None:
                    item.id = 1
                self.added.append(item)

            def flush(self):
                for item in self.added:
                    if isinstance(item, Submission) and getattr(item, "id", None) is None:
                        item.id = 1

            def commit(self):
                self.committed = True

        self.db = _FakeSession(problem)

    def test_submit_auditor_report_updates_submission_and_analysis(self):
        evaluation = {
            "summary": "핵심 함정을 잘 짚었습니다.",
            "strengths": ["영향도 분석이 정확합니다."],
            "improvements": ["완화 방안을 더 구체화하세요."],
            "score": 84.0,
            "correct": True,
            "found_types": ["logic_error"],
            "missed_types": ["injection_risk"],
        }
        with (
            patch("app.services.auditor_service._ai_client.analyze_auditor_report", return_value=evaluation),
            patch("app.services.auditor_service.update_user_problem_stat") as mock_stat_update,
        ):
            result = submit_auditor_report(
                self.db,
                user_id=1,
                problem_id="101",
                report="검토 결과 로직 오류와 보안 취약점을 확인했습니다.",
            )

        self.assertEqual(result["verdict"], "passed")
        self.assertGreaterEqual(result["score"], 70.0)

        submission = next((item for item in self.db.added if isinstance(item, Submission)), None)
        self.assertIsNotNone(submission)
        self.assertEqual(submission.status.value, "passed")
        self.assertIsNotNone(submission.score)

        analysis = next((item for item in self.db.added if isinstance(item, AIAnalysis)), None)
        self.assertIsNotNone(analysis)
        self.assertIn("핵심 함정을 잘 짚었습니다.", analysis.result_summary)

        mock_stat_update.assert_called_once()
        self.assertTrue(self.db.committed)

    def test_submit_blank_report_rejected(self):
        with self.assertRaises(ValueError):
            submit_auditor_report(
                self.db,
                user_id=1,
                problem_id="101",
                report="   ",
            )

    def test_submit_ai_failure_returns_fallback_response(self):
        with (
            patch("app.services.auditor_service._ai_client.analyze_auditor_report", side_effect=RuntimeError("ai down")),
            patch("app.services.auditor_service.update_user_problem_stat") as mock_stat_update,
        ):
            result = submit_auditor_report(
                self.db,
                user_id=1,
                problem_id="101",
                report="리포트",
            )

        self.assertEqual(result["verdict"], "failed")
        self.assertEqual(result["score"], 0.0)
        self.assertIn("AI 채점 중 오류", result["feedback"]["summary"])
        analysis = next((item for item in self.db.added if isinstance(item, AIAnalysis)), None)
        self.assertIsNotNone(analysis)
        self.assertIn("ai down", analysis.result_detail)
        mock_stat_update.assert_called_once()
        self.assertTrue(self.db.committed)

    def test_create_problem_generation_failure_returns_user_friendly_error(self):
        class _NoopDB:
            pass

        with patch(
            "app.services.auditor_service._generator.generate_auditor_problem_sync",
            side_effect=RuntimeError("generator down"),
        ):
            with self.assertRaisesRegex(ValueError, "문제 생성에 실패했습니다."):
                create_auditor_problem(
                    _NoopDB(),
                    user_id=1,
                    language="python",
                    difficulty="beginner",
                )


if __name__ == "__main__":
    unittest.main()
