from dataclasses import dataclass
from typing import Protocol, Literal, Any

@dataclass
class AnalysisResult:
    status: Literal["passed", "failed"]
    score: int
    summary: str
    detail: Any

class AIProvider(Protocol):
    def analyze(self, *, language: str, code: str, problem_prompt: str) -> AnalysisResult:
        ...
