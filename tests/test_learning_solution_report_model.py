from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.ai_client import AIClient, LEARNING_REPORT_MODEL


def _valid_plan_payload() -> dict[str, object]:
    return {
        "goal": "다음 2주 동안 알고리즘 풀이 루틴을 안정화한다.",
        "solutionSummary": "매일 짧은 루틴과 주간 회고를 통해 문제 해결 속도와 정확도를 함께 끌어올린다.",
        "priorityActions": ["오답 노트 3개 복기", "매일 2문제 풀이"],
        "phasePlan": ["1주차: 기초 재정비", "2주차: 실전 적용"],
        "dailyHabits": ["25분 집중 풀이", "10분 회고 작성"],
        "focusTopics": ["투 포인터", "해시"],
        "metricsToTrack": ["정확도", "평균 풀이 시간"],
        "checkpoints": ["주간 정확도 70% 달성", "오답 재풀이 완료"],
        "riskMitigation": ["난이도 급상승 금지", "실패 문제 재시도"],
    }


class _FakeMetrics:
    def __init__(self) -> None:
        self.tokens: list[object] = []
        self.events: list[tuple[object, bool]] = []

    def start_ai_call(self, provider: str = "google", operation: str = "unknown") -> object:
        token = {"provider": provider, "operation": operation}
        self.tokens.append(token)
        return token

    def end_ai_call(self, token: object, success: bool) -> None:
        self.events.append((token, success))


class _FakeModels:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def generate_content(self, *, model: str, contents: str, config: object) -> object:
        self.calls.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(text=json.dumps(self.payload, ensure_ascii=False))


class LearningSolutionReportModelTests(unittest.TestCase):
    def test_uses_fixed_model_and_low_thinking(self) -> None:
        ai = AIClient()
        fake_models = _FakeModels(_valid_plan_payload())
        ai.client = SimpleNamespace(models=fake_models)
        ai.metrics = _FakeMetrics()

        result = ai.generate_learning_solution_report(
            history_context="1. [정답] 문제 A",
            metric_snapshot={"attempts": 10, "accuracy": 70.0, "avgScore": 75.5, "trend": "stable"},
        )

        self.assertEqual(fake_models.calls[0]["model"], LEARNING_REPORT_MODEL)
        config = fake_models.calls[0]["config"]
        self.assertEqual(str(config.thinking_config.thinking_level).split(".")[-1].lower(), "low")
        self.assertEqual(result["goal"], _valid_plan_payload()["goal"])
        self.assertIn("priorityActions", result)

    def test_retries_once_then_succeeds(self) -> None:
        ai = AIClient()
        ai.client = object()
        success_response = SimpleNamespace(text=json.dumps(_valid_plan_payload(), ensure_ascii=False))

        with patch.object(
            ai,
            "_generate_learning_report_once",
            side_effect=[RuntimeError("first fail"), success_response],
        ) as mocked:
            result = ai.generate_learning_solution_report(
                history_context="history",
                metric_snapshot={"attempts": 1, "accuracy": None, "avgScore": None, "trend": "insufficient"},
            )

        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(result["goal"], _valid_plan_payload()["goal"])

    def test_raises_after_retry_exhausted(self) -> None:
        ai = AIClient()
        ai.client = object()

        with patch.object(ai, "_generate_learning_report_once", side_effect=RuntimeError("fail")):
            with self.assertRaises(RuntimeError) as ctx:
                ai.generate_learning_solution_report(
                    history_context="history",
                    metric_snapshot={"attempts": 1, "accuracy": None, "avgScore": None, "trend": "insufficient"},
                )
        self.assertIn("learning_report_generation_failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
