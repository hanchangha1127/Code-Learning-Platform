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
from app.services.refactoring_choice_service import (
    create_refactoring_choice_problem,
    map_refactoring_choice_difficulty,
    submit_refactoring_choice_report,
)
from backend.learning_mode_handlers import (
    REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY,
    REFACTORING_CHOICE_FACET_TAXONOMY,
    REFACTORING_CHOICE_OPTION_IDS,
)
from server_runtime.schemas import RefactoringChoiceSubmitRequest


class RefactoringChoiceSchemaTests(unittest.TestCase):
    def test_submit_request_accepts_aliases(self):
        first = RefactoringChoiceSubmitRequest(problemId="p1", selectedOption="a", report="리포트")
        second = RefactoringChoiceSubmitRequest(problem_id="p2", selected_option="b", report="리포트")

        self.assertEqual(first.problem_id, "p1")
        self.assertEqual(second.problem_id, "p2")
        self.assertEqual(first.selected_option, "A")
        self.assertEqual(second.selected_option, "B")

    def test_submit_request_strips_report_whitespace(self):
        item = RefactoringChoiceSubmitRequest(problemId="p1", selectedOption="C", report="  리포트  ")
        self.assertEqual(item.report, "리포트")


class RefactoringChoiceMappingTests(unittest.TestCase):
    def test_option_ids_fixed(self):
        self.assertEqual(REFACTORING_CHOICE_OPTION_IDS, ("A", "B", "C"))

    def test_constraint_count_mapping(self):
        self.assertEqual(REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY["beginner"], 2)
        self.assertEqual(REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY["intermediate"], 3)
        self.assertEqual(REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY["advanced"], 4)

    def test_facet_taxonomy_fixed(self):
        self.assertEqual(
            set(REFACTORING_CHOICE_FACET_TAXONOMY),
            {"performance", "memory", "readability", "maintainability", "security", "testability"},
        )

    def test_platform_difficulty_mapping(self):
        self.assertEqual(map_refactoring_choice_difficulty("beginner"), ProblemDifficulty.easy)
        self.assertEqual(map_refactoring_choice_difficulty("intermediate"), ProblemDifficulty.medium)
        self.assertEqual(map_refactoring_choice_difficulty("advanced"), ProblemDifficulty.hard)
        with self.assertRaises(ValueError):
            map_refactoring_choice_difficulty("expert")


class RefactoringChoiceSqlSubmitTests(unittest.TestCase):
    def setUp(self) -> None:
        problem = Problem(
            id=301,
            kind=ProblemKind.refactoring_choice,
            title="최적의 선택 테스트",
            description="A/B/C 중 최적안을 고르고 근거를 작성하세요.",
            difficulty=ProblemDifficulty.easy,
            language="python",
            starter_code="메모리 제한이 강한 환경",
            options={
                "scenario": "메모리 제한이 강한 환경",
                "constraints": ["메모리 32MB", "응답 지연 최소화"],
                "options": [
                    {"optionId": "A", "title": "반복문", "code": "for i in range(n): pass"},
                    {"optionId": "B", "title": "제너레이터", "code": "def run():\n    yield from range(n)"},
                    {"optionId": "C", "title": "리스트 누적", "code": "buf = [i for i in range(n)]"},
                ],
                "decision_facets": ["performance", "memory", "maintainability"],
                "best_option": "B",
                "reference_report": "모범 의사결정 메모",
                "option_reviews": [
                    {"optionId": "A", "summary": "단순하지만 확장성이 낮음"},
                    {"optionId": "B", "summary": "메모리 사용량이 가장 낮음"},
                    {"optionId": "C", "summary": "메모리 부담이 큼"},
                ],
                "client_difficulty": "beginner",
            },
            reference_solution="모범 의사결정 메모",
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

    def test_submit_report_updates_submission_and_analysis(self):
        evaluation = {
            "summary": "제약 기반 의사결정이 명확합니다.",
            "strengths": ["메모리 제약을 정확히 반영했습니다."],
            "improvements": ["유지보수 관점 보완이 필요합니다."],
            "score": 82.0,
            "correct": True,
            "found_types": ["memory", "performance"],
            "missed_types": ["maintainability"],
        }
        with (
            patch("app.services.refactoring_choice_service._ai_client.analyze_refactoring_choice_report", return_value=evaluation),
            patch("app.services.refactoring_choice_service.update_user_problem_stat") as mock_stat_update,
        ):
            result = submit_refactoring_choice_report(
                self.db,
                user_id=1,
                problem_id="301",
                selected_option="B",
                report="B가 메모리 사용량을 줄이고 응답 지연을 낮출 수 있습니다.",
            )

        self.assertEqual(result["verdict"], "passed")
        self.assertGreaterEqual(result["score"], 70.0)
        self.assertEqual(result["selectedOption"], "B")
        self.assertEqual(result["bestOption"], "B")

        submission = next((item for item in self.db.added if isinstance(item, Submission)), None)
        self.assertIsNotNone(submission)
        self.assertEqual(submission.status.value, "passed")
        self.assertIn('"selectedOption": "B"', submission.code)

        analysis = next((item for item in self.db.added if isinstance(item, AIAnalysis)), None)
        self.assertIsNotNone(analysis)
        self.assertIn("제약 기반 의사결정이 명확합니다.", analysis.result_summary)

        mock_stat_update.assert_called_once()
        self.assertTrue(self.db.committed)

    def test_submit_invalid_selected_option_rejected(self):
        with self.assertRaises(ValueError):
            submit_refactoring_choice_report(
                self.db,
                user_id=1,
                problem_id="301",
                selected_option="Z",
                report="근거",
            )

    def test_submit_ai_failure_returns_fallback_response(self):
        with (
            patch(
                "app.services.refactoring_choice_service._ai_client.analyze_refactoring_choice_report",
                side_effect=RuntimeError("ai down"),
            ),
            patch("app.services.refactoring_choice_service.update_user_problem_stat") as mock_stat_update,
        ):
            result = submit_refactoring_choice_report(
                self.db,
                user_id=1,
                problem_id="301",
                selected_option="B",
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
            "app.services.refactoring_choice_service._generator.generate_refactoring_choice_problem_sync",
            side_effect=RuntimeError("generator down"),
        ):
            with self.assertRaisesRegex(ValueError, "문제 생성에 실패했습니다."):
                create_refactoring_choice_problem(
                    _NoopDB(),
                    user_id=1,
                    language="python",
                    difficulty="beginner",
                )


if __name__ == "__main__":
    unittest.main()
