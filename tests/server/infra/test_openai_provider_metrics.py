import json
import unittest
from unittest.mock import Mock, patch

from server.features.learning.ai_providers.openai_provider import OpenAIProvider


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class OpenAIProviderMetricsTests(unittest.TestCase):
    def test_analyze_records_admin_metrics_on_success(self) -> None:
        metrics = Mock()
        metrics.start_ai_call.return_value = "token-1"
        provider = OpenAIProvider(api_key="test-key", metrics=metrics)
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "status": "passed",
                                "score": 92,
                                "summary": "looks_good",
                                "detail": {"strengths": ["coverage"]},
                            }
                        )
                    }
                }
            ]
        }

        with patch(
            "server.features.learning.ai_providers.openai_provider.request.urlopen",
            return_value=_FakeHTTPResponse(payload),
        ):
            result = provider.analyze(
                language="python",
                code="print('ok')",
                problem_prompt="Return the expected output.",
            )

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.score, 92)
        metrics.start_ai_call.assert_called_once_with(
            provider="openai",
            operation="submission_analysis",
        )
        metrics.end_ai_call.assert_called_once_with("token-1", success=True)

    def test_analyze_records_admin_metrics_on_failure(self) -> None:
        metrics = Mock()
        metrics.start_ai_call.return_value = "token-2"
        provider = OpenAIProvider(api_key="test-key", metrics=metrics)

        with patch(
            "server.features.learning.ai_providers.openai_provider.request.urlopen",
            side_effect=RuntimeError("network down"),
        ):
            with self.assertRaises(RuntimeError):
                provider.analyze(
                    language="python",
                    code="print('ok')",
                    problem_prompt="Return the expected output.",
                )

        metrics.start_ai_call.assert_called_once_with(
            provider="openai",
            operation="submission_analysis",
        )
        metrics.end_ai_call.assert_called_once_with("token-2", success=False)


if __name__ == "__main__":
    unittest.main()

