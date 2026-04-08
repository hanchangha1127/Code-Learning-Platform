from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server.infra.ai_client import AIClient, LEARNING_REPORT_MODEL


def _valid_plan_payload() -> dict[str, object]:
    return {
        "goal": "Set a firm report and practice routine for the next two weeks.",
        "solutionSummary": "Daily practice and weekly review raise both solving speed and accuracy.",
        "priorityActions": ["Read 3 wrong-answer notes", "Solve 2 problems every day"],
        "phasePlan": ["Week 1: rebuild fundamentals", "Week 2: apply them in practice"],
        "dailyHabits": ["25 minutes of focused solving", "10 minutes of review notes"],
        "focusTopics": ["conditionals", "iteration"],
        "metricsToTrack": ["accuracy", "average solve time"],
        "checkpoints": ["Reach 70% weekly accuracy", "Finish the wrong-answer notebook"],
        "riskMitigation": ["Avoid overlong explanations", "Retry failed problems"],
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

    def test_includes_detail_records_in_prompt(self) -> None:
        ai = AIClient()
        fake_models = _FakeModels(_valid_plan_payload())
        ai.client = SimpleNamespace(models=fake_models)
        ai.metrics = _FakeMetrics()

        ai.generate_learning_solution_report(
            history_context="1. [오답] 문제 A",
            metric_snapshot={"attempts": 2, "accuracy": 50.0, "avgScore": 60.0, "trend": "stable"},
            detail_records=[
                {
                    "title": "문제 A",
                    "result": "incorrect",
                    "learnerResponse": "선택: B",
                    "expectedAnswer": "선택: A",
                    "evaluation": {"wrongType": "logic_error", "comparison": "정답은 A인데 B를 선택했습니다."},
                }
            ],
        )

        contents = fake_models.calls[0]["contents"]
        self.assertIn("=== 문제별 세부 내역 ===", contents)
        self.assertIn("문제 A", contents)
        self.assertIn("logic_error", contents)

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

