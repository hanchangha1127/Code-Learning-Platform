from .base import AnalysisResult

class MockAIProvider:
    def analyze(self, *, language: str, code: str, problem_prompt: str) -> AnalysisResult:
        return AnalysisResult(
            status="passed",
            score=100,
            summary="mock_passed",
            detail={"message": "All test cases passed (mock)."},
        )
