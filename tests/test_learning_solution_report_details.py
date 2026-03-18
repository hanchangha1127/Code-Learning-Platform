from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.db.models import (
    AIAnalysis,
    AnalysisType,
    Problem,
    ProblemDifficulty,
    ProblemKind,
    Submission,
    SubmissionStatus,
    UserProblemStat,
)
from app.services import report_service
from backend import learning_reporting


def _solution_plan() -> dict[str, object]:
    return {
        "goal": "오답 패턴을 줄이기 위한 주간 목표를 세운다.",
        "solutionSummary": "문제별 오답 원인을 바탕으로 재학습 루틴을 구성한다.",
        "priorityActions": ["오답 복기 3개", "반례 노트 정리"],
        "phasePlan": ["1주차: 오답 복기", "2주차: 재도전"],
        "dailyHabits": ["매일 2문제 풀이"],
        "focusTopics": ["조건 분기", "반례 검증"],
        "metricsToTrack": ["정확도", "logic_error 감소"],
        "checkpoints": ["주말 정확도 70% 달성"],
        "riskMitigation": ["틀린 문제는 즉시 복기"],
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
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        pass

    def refresh(self, obj: object) -> None:
        setattr(obj, "id", 901)
        if getattr(obj, "created_at", None) is None:
            setattr(obj, "created_at", datetime.now(timezone.utc))


class LearningSolutionReportDetailTests(unittest.TestCase):
    def test_legacy_learning_report_passes_per_problem_details(self) -> None:
        history = [
            {
                "mode": "code-block",
                "problem_title": "조건문 빈칸 채우기",
                "correct": False,
                "score": 30,
                "feedback": {
                    "summary": "비교 연산자를 잘못 선택했습니다.",
                    "strengths": ["반복문 구조는 이해했습니다."],
                    "improvements": ["조건 경계값을 다시 확인하세요."],
                },
                "duration_seconds": 18,
                "problem_prompt": "빈칸에 올바른 조건식을 넣으세요.",
                "problem_code": "for i in range(3):\n    if ____:\n        print(i)",
                "problem_options": ["i < 3", "i <= 3"],
                "selected_option_text": "i <= 3",
                "correct_option_text": "i < 3",
                "selected_option": 1,
                "correct_answer_index": 0,
                "summary": "조건식 선택 문제",
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
        captured = service.captured or {}
        detail_records = captured.get("detail_records")
        self.assertIsInstance(detail_records, list)
        record = detail_records[0]
        self.assertEqual(record["title"], "조건문 빈칸 채우기")
        self.assertEqual(record["expectedAnswer"], "i < 3")
        self.assertIn("정답은", record["evaluation"]["comparison"])

    def test_milestone_report_passes_detailed_submission_records(self) -> None:
        now = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc)
        problem = Problem(
            id=21,
            external_id="prob-21",
            kind=ProblemKind.coding,
            title="배열 합 구하기",
            description="배열의 합을 반환하세요.",
            difficulty=ProblemDifficulty.medium,
            language="python",
            starter_code="def solve(nums):\n    pass",
            problem_payload={"prompt": "배열의 합을 반환하세요."},
            answer_payload={},
        )
        submission = Submission(
            id=11,
            user_id=1,
            problem_id=21,
            language="python",
            code="def solve(nums):\n    return nums[0]",
            submission_payload={"bridgeId": "bridge-11"},
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
                    "summary": "첫 원소만 반환해서 누적 로직이 빠졌습니다.",
                    "strengths": ["함수 시그니처는 맞았습니다."],
                    "improvements": ["반복 누적 또는 sum 사용을 검토하세요."],
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

        fake_db = _FakeDB()
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
        detail_records = captured.get("detail_records")
        self.assertIsInstance(detail_records, list)
        record = detail_records[0]
        self.assertEqual(record["title"], "배열 합 구하기")
        self.assertEqual(record["evaluation"]["wrongType"], "logic_error")
        self.assertIn("누적 로직", record["evaluation"]["feedbackSummary"])


if __name__ == "__main__":
    unittest.main()
