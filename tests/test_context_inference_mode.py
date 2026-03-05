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
from app.services.context_inference_service import (
    create_context_inference_problem,
    map_context_inference_difficulty,
    submit_context_inference_report,
)
from backend.learning_mode_handlers import (
    CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY,
    CONTEXT_INFERENCE_TYPE_WEIGHTS,
)
from server_runtime.schemas import ContextInferenceSubmitRequest


class ContextInferenceSchemaTests(unittest.TestCase):
    def test_context_inference_submit_request_accepts_aliases(self):
        first = ContextInferenceSubmitRequest(problemId="p1", report="리포트")
        second = ContextInferenceSubmitRequest(problem_id="p2", report="리포트")

        self.assertEqual(first.problem_id, "p1")
        self.assertEqual(second.problem_id, "p2")

    def test_context_inference_submit_request_strips_report_whitespace(self):
        item = ContextInferenceSubmitRequest(problemId="p1", report="  리포트  ")
        self.assertEqual(item.report, "리포트")


class ContextInferenceMappingTests(unittest.TestCase):
    def test_type_weight_mapping(self):
        self.assertEqual(CONTEXT_INFERENCE_TYPE_WEIGHTS["beginner"], {"pre_condition": 70, "post_condition": 30})
        self.assertEqual(CONTEXT_INFERENCE_TYPE_WEIGHTS["intermediate"], {"pre_condition": 50, "post_condition": 50})
        self.assertEqual(CONTEXT_INFERENCE_TYPE_WEIGHTS["advanced"], {"pre_condition": 30, "post_condition": 70})

    def test_complexity_profile_mapping(self):
        self.assertEqual(
            CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY["beginner"],
            "single_function_local_state",
        )
        self.assertEqual(
            CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY["intermediate"],
            "service_plus_repository_side_effect",
        )
        self.assertEqual(
            CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY["advanced"],
            "multi_stage_transaction_auth_concurrency",
        )

    def test_platform_difficulty_mapping(self):
        self.assertEqual(map_context_inference_difficulty("beginner"), ProblemDifficulty.easy)
        self.assertEqual(map_context_inference_difficulty("intermediate"), ProblemDifficulty.medium)
        self.assertEqual(map_context_inference_difficulty("advanced"), ProblemDifficulty.hard)
        with self.assertRaises(ValueError):
            map_context_inference_difficulty("expert")


class ContextInferenceSqlSubmitTests(unittest.TestCase):
    def setUp(self) -> None:
        problem = Problem(
            id=201,
            kind=ProblemKind.context_inference,
            title="맥락 추론 테스트",
            description="이 함수 실행 전 상태를 추론하세요.",
            difficulty=ProblemDifficulty.easy,
            language="python",
            starter_code="def apply(items):\n    return [x + 1 for x in items]",
            options={
                "expected_facets": [
                    "input_shape",
                    "state_transition",
                    "side_effect",
                ],
                "reference_report": "모범 추론 리포트",
                "inference_type": "pre_condition",
                "client_difficulty": "beginner",
            },
            reference_solution="모범 추론 리포트",
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

    def test_submit_context_inference_report_updates_submission_and_analysis(self):
        evaluation = {
            "summary": "핵심 맥락을 잘 짚었습니다.",
            "strengths": ["입력 조건과 상태 변화를 명확히 설명했습니다."],
            "improvements": ["부작용 시나리오를 한 단계 더 구체화하세요."],
            "score": 86.0,
            "correct": True,
            "found_types": ["input_shape", "state_transition"],
            "missed_types": ["side_effect"],
        }
        with (
            patch("app.services.context_inference_service._ai_client.analyze_context_inference_report", return_value=evaluation),
            patch("app.services.context_inference_service.update_user_problem_stat") as mock_stat_update,
        ):
            result = submit_context_inference_report(
                self.db,
                user_id=1,
                problem_id="201",
                report="입력은 리스트 형태이고 실행 후 각 원소가 증가합니다.",
            )

        self.assertEqual(result["verdict"], "passed")
        self.assertGreaterEqual(result["score"], 70.0)

        submission = next((item for item in self.db.added if isinstance(item, Submission)), None)
        self.assertIsNotNone(submission)
        self.assertEqual(submission.status.value, "passed")
        self.assertIsNotNone(submission.score)

        analysis = next((item for item in self.db.added if isinstance(item, AIAnalysis)), None)
        self.assertIsNotNone(analysis)
        self.assertIn("핵심 맥락을 잘 짚었습니다.", analysis.result_summary)

        mock_stat_update.assert_called_once()
        self.assertTrue(self.db.committed)

    def test_submit_blank_report_rejected(self):
        with self.assertRaises(ValueError):
            submit_context_inference_report(
                self.db,
                user_id=1,
                problem_id="201",
                report="   ",
            )

    def test_submit_ai_failure_returns_fallback_response(self):
        with (
            patch(
                "app.services.context_inference_service._ai_client.analyze_context_inference_report",
                side_effect=RuntimeError("ai down"),
            ),
            patch("app.services.context_inference_service.update_user_problem_stat") as mock_stat_update,
        ):
            result = submit_context_inference_report(
                self.db,
                user_id=1,
                problem_id="201",
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
            "app.services.context_inference_service._generator.generate_context_inference_problem_sync",
            side_effect=RuntimeError("generator down"),
        ):
            with self.assertRaisesRegex(ValueError, "문제 생성에 실패했습니다."):
                create_context_inference_problem(
                    _NoopDB(),
                    user_id=1,
                    language="python",
                    difficulty="beginner",
                )


if __name__ == "__main__":
    unittest.main()
