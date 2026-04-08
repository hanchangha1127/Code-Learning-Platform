from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError

from server.db.models import (
    AIAnalysis,
    Problem,
    ProblemDifficulty,
    ProblemKind,
    Submission,
)
from server.features.learning.code_blame_service import create_code_blame_problem, map_code_blame_difficulty, submit_code_blame_report
from server.features.learning.service import (
    CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY,
    CODE_BLAME_CULPRIT_COUNT_WEIGHTS,
)
from server.schemas.runtime import CodeBlameSubmitRequest


class CodeBlameSchemaTests(unittest.TestCase):
    def test_submit_request_accepts_aliases(self):
        first = CodeBlameSubmitRequest(problemId="p1", selectedCommits=["a"], report="리포트")
        second = CodeBlameSubmitRequest(problem_id="p2", selected_commits=["b", "c"], report="리포트")

        self.assertEqual(first.problem_id, "p1")
        self.assertEqual(second.problem_id, "p2")
        self.assertEqual(first.selected_commits, ["A"])
        self.assertEqual(second.selected_commits, ["B", "C"])

    def test_submit_request_rejects_duplicates(self):
        with self.assertRaises(ValidationError):
            CodeBlameSubmitRequest(problemId="p1", selectedCommits=["A", "A"], report="리포트")


class CodeBlameMappingTests(unittest.TestCase):
    def test_candidate_count_mapping(self):
        self.assertEqual(CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY["beginner"], 3)
        self.assertEqual(CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY["intermediate"], 4)
        self.assertEqual(CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY["advanced"], 5)

    def test_culprit_weight_mapping(self):
        self.assertEqual(CODE_BLAME_CULPRIT_COUNT_WEIGHTS[1], 70)
        self.assertEqual(CODE_BLAME_CULPRIT_COUNT_WEIGHTS[2], 30)

    def test_platform_difficulty_mapping(self):
        self.assertEqual(map_code_blame_difficulty("beginner"), ProblemDifficulty.easy)
        self.assertEqual(map_code_blame_difficulty("intermediate"), ProblemDifficulty.medium)
        self.assertEqual(map_code_blame_difficulty("advanced"), ProblemDifficulty.hard)
        with self.assertRaises(ValueError):
            map_code_blame_difficulty("expert")


class CodeBlameSqlSubmitTests(unittest.TestCase):
    def setUp(self) -> None:
        problem = Problem(
            id=401,
            kind=ProblemKind.code_blame,
            title="범인 찾기 테스트",
            description="에러 로그와 diff를 비교해 범인을 찾으세요.",
            difficulty=ProblemDifficulty.easy,
            language="python",
            starter_code="Traceback ... KeyError: 'user_id'",
            options={
                "commits": [
                    {"optionId": "A", "title": "cache refactor", "diff": "diff --git a/a b/a"},
                    {"optionId": "B", "title": "auth check removal", "diff": "diff --git a/b b/b"},
                    {"optionId": "C", "title": "logging tweak", "diff": "diff --git a/c b/c"},
                ],
                "culprit_commits": ["B"],
                "decision_facets": ["log_correlation", "root_cause_diff", "failure_mechanism"],
                "reference_report": "모범 리포트",
                "commit_reviews": [
                    {"optionId": "A", "summary": "가능성 낮음"},
                    {"optionId": "B", "summary": "핵심 원인"},
                    {"optionId": "C", "summary": "부수적 변경"},
                ],
                "candidate_count": 3,
                "culprit_count": 1,
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
            "summary": "로그와 diff를 잘 연결했습니다.",
            "strengths": ["범인 커밋을 정확히 특정했습니다."],
            "improvements": ["영향 범위를 한 단계 더 구체화하세요."],
            "score": 81.0,
            "correct": True,
            "found_types": ["log_correlation", "root_cause_diff"],
            "missed_types": ["failure_mechanism"],
        }
        with (
            patch("server.features.learning.code_blame_service._ai_client.analyze_code_blame_report", return_value=evaluation),
            patch("server.features.learning.code_blame_service.update_user_problem_stat") as mock_stat_update,
        ):
            result = submit_code_blame_report(
                self.db,
                user_id=1,
                problem_id="401",
                selected_commits=["B"],
                report="로그의 KeyError와 B 커밋의 인증 변경이 직접 연결됩니다.",
            )

        self.assertEqual(result["verdict"], "passed")
        self.assertGreaterEqual(result["score"], 70.0)
        self.assertEqual(result["selectedCommits"], ["B"])
        self.assertEqual(result["culpritCommits"], ["B"])

        submission = next((item for item in self.db.added if isinstance(item, Submission)), None)
        self.assertIsNotNone(submission)
        self.assertEqual(submission.status.value, "passed")
        self.assertIn('"selectedCommits": ["B"]', submission.code)

        analysis = next((item for item in self.db.added if isinstance(item, AIAnalysis)), None)
        self.assertIsNotNone(analysis)
        self.assertIn("로그와 diff를 잘 연결했습니다.", analysis.result_summary)

        mock_stat_update.assert_called_once()
        self.assertTrue(self.db.committed)

    def test_submit_invalid_commit_rejected(self):
        with self.assertRaises(ValueError):
            submit_code_blame_report(
                self.db,
                user_id=1,
                problem_id="401",
                selected_commits=["Z"],
                report="리포트",
            )

    def test_submit_ai_failure_returns_fallback_response(self):
        with (
            patch("server.features.learning.code_blame_service._ai_client.analyze_code_blame_report", side_effect=RuntimeError("ai down")),
            patch("server.features.learning.code_blame_service.update_user_problem_stat") as mock_stat_update,
        ):
            result = submit_code_blame_report(
                self.db,
                user_id=1,
                problem_id="401",
                selected_commits=["B"],
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
            "server.features.learning.code_blame_service._generator.generate_code_blame_problem_sync",
            side_effect=RuntimeError("generator down"),
        ):
            with self.assertRaisesRegex(ValueError, "문제 생성에 실패했습니다."):
                create_code_blame_problem(
                    _NoopDB(),
                    user_id=1,
                    language="python",
                    difficulty="beginner",
                )


if __name__ == "__main__":
    unittest.main()
