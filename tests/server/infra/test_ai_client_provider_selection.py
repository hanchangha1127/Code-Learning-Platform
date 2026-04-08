from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server.infra.ai_client import AIClient


class _FakeMetrics:
    def start_ai_call(self, provider: str = "unknown", operation: str = "unknown") -> object:
        return {"provider": provider, "operation": operation}

    def end_ai_call(self, token: object, success: bool) -> None:
        return None


def _openai_settings() -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider="openai",
        google_api_key=None,
        ai_api_key=None,
        resolved_openai_api_key="sk-test",
        openai_model="gpt-4o-mini",
        google_model="gemini-3-flash-preview",
        google_timeout_seconds=30,
        ai_request_timeout_seconds=15,
    )


def _plan_payload() -> dict[str, object]:
    return {
        "goal": "핵심 개념을 다시 정리하고 주간 루틴을 고정하세요.",
        "solutionSummary": "최근 오답 패턴을 기준으로 실행 계획을 다시 세웁니다.",
        "priorityActions": ["핵심 문제 3개 복습"],
        "phasePlan": ["1주차: 기본기 복습"],
        "dailyHabits": ["매일 30분 코드 리뷰"],
        "focusTopics": ["조건 분기"],
        "metricsToTrack": ["정확도"],
        "checkpoints": ["주간 회고 작성"],
        "riskMitigation": ["오답 노트를 유지하세요."],
    }


class AIClientProviderSelectionTests(unittest.TestCase):
    def test_initializes_openai_provider_when_configured(self) -> None:
        with (
            patch("server.infra.ai_client.get_settings", return_value=_openai_settings()),
            patch("server.infra.ai_client.get_admin_metrics", return_value=_FakeMetrics()),
        ):
            ai = AIClient()

        self.assertEqual(ai.provider, "openai")
        self.assertEqual(ai.model, "gpt-4o-mini")
        self.assertEqual(ai.openai_api_key, "sk-test")
        self.assertIsNone(ai.client)

    def test_refactoring_choice_uses_openai_when_configured(self) -> None:
        response = SimpleNamespace(
            text=json.dumps(
                {
                    "summary": "제약과 트레이드오프를 잘 비교했습니다.",
                    "strengths": ["선택 근거가 구체적입니다."],
                    "improvements": ["제약별 우선순위를 더 명확히 적어보세요."],
                    "score": 87,
                    "correct": True,
                    "found_types": ["performance", "memory"],
                },
                ensure_ascii=False,
            )
        )

        with (
            patch("server.infra.ai_client.get_settings", return_value=_openai_settings()),
            patch("server.infra.ai_client.get_admin_metrics", return_value=_FakeMetrics()),
        ):
            ai = AIClient()

        with patch.object(ai, "_request_openai_text", return_value=response) as mocked:
            result = ai.analyze_refactoring_choice_report(
                scenario="high traffic API",
                prompt="가장 적절한 선택지를 고르세요.",
                constraints=["latency", "memory"],
                options=[
                    {"optionId": "A", "title": "A", "code": "pass"},
                    {"optionId": "B", "title": "B", "code": "pass"},
                    {"optionId": "C", "title": "C", "code": "pass"},
                ],
                selected_option="B",
                best_option="B",
                report="B가 지연 시간과 메모리 제약을 가장 잘 만족합니다.",
                decision_facets=["performance", "memory", "maintainability"],
                reference_report="모범 리포트",
                option_reviews=[],
                language="python",
                difficulty="beginner",
            )

        self.assertTrue(mocked.called)
        self.assertEqual(result["feedback_source"], "ai")
        self.assertEqual(result["ai_provider"], "openai")
        self.assertEqual(result["score"], 87.0)

    def test_learning_solution_report_uses_openai_request_path(self) -> None:
        response = SimpleNamespace(text=json.dumps(_plan_payload(), ensure_ascii=False))

        with (
            patch("server.infra.ai_client.get_settings", return_value=_openai_settings()),
            patch("server.infra.ai_client.get_admin_metrics", return_value=_FakeMetrics()),
        ):
            ai = AIClient()

        with patch.object(ai, "_request_openai_text", return_value=response) as mocked:
            result = ai.generate_learning_solution_report(
                history_context="1. [정답] 문제 A",
                metric_snapshot={"attempts": 3, "accuracy": 66.0, "avgScore": 72.0, "trend": "stable"},
            )

        self.assertTrue(mocked.called)
        self.assertEqual(mocked.call_args.kwargs["operation"], "learning_report_generation")
        self.assertEqual(result["goal"], _plan_payload()["goal"])


if __name__ == "__main__":
    unittest.main()
