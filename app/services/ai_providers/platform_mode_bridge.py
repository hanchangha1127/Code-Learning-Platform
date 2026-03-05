from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.ai_client import AIClient
    from backend.problem_generator import ProblemGenerator


class PlatformModeAIBridge:
    def __init__(
        self,
        *,
        generator: ProblemGenerator | None = None,
        ai_client: AIClient | None = None,
    ):
        if generator is None:
            from backend.problem_generator import ProblemGenerator as _ProblemGenerator

            generator = _ProblemGenerator()
        if ai_client is None:
            from backend.ai_client import AIClient as _AIClient

            ai_client = _AIClient()

        self._generator = generator
        self._ai_client = ai_client

    def generate_auditor_problem_sync(self, **kwargs: Any) -> dict[str, Any]:
        return self._generator.generate_auditor_problem_sync(**kwargs)

    def analyze_auditor_report(self, **kwargs: Any) -> dict[str, Any]:
        return self._ai_client.analyze_auditor_report(**kwargs)

    def generate_context_inference_problem_sync(self, **kwargs: Any) -> dict[str, Any]:
        return self._generator.generate_context_inference_problem_sync(**kwargs)

    def analyze_context_inference_report(self, **kwargs: Any) -> dict[str, Any]:
        return self._ai_client.analyze_context_inference_report(**kwargs)

    def generate_refactoring_choice_problem_sync(self, **kwargs: Any) -> dict[str, Any]:
        return self._generator.generate_refactoring_choice_problem_sync(**kwargs)

    def analyze_refactoring_choice_report(self, **kwargs: Any) -> dict[str, Any]:
        return self._ai_client.analyze_refactoring_choice_report(**kwargs)

    def generate_code_blame_problem_sync(self, **kwargs: Any) -> dict[str, Any]:
        return self._generator.generate_code_blame_problem_sync(**kwargs)

    def analyze_code_blame_report(self, **kwargs: Any) -> dict[str, Any]:
        return self._ai_client.analyze_code_blame_report(**kwargs)


@lru_cache(maxsize=1)
def get_platform_mode_ai_bridge() -> PlatformModeAIBridge:
    return PlatformModeAIBridge()
