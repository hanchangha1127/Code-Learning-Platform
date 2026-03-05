from __future__ import annotations

from typing import Any, Iterable, Mapping

DEFAULT_FALLBACK_SUMMARY = "AI 채점 중 오류가 발생해 기본 실패 응답을 반환했습니다. 잠시 후 다시 시도해주세요."
DEFAULT_FALLBACK_IMPROVEMENT = "리포트 내용을 유지한 채 재시도해주세요."


def build_ai_evaluation_fallback(
    *,
    missed_types: Iterable[str] | None,
    error: Exception | str | None,
    summary: str = DEFAULT_FALLBACK_SUMMARY,
    improvement: str = DEFAULT_FALLBACK_IMPROVEMENT,
) -> dict[str, Any]:
    return {
        "summary": summary,
        "strengths": [],
        "improvements": [improvement],
        "score": 0.0,
        "correct": False,
        "found_types": [],
        "missed_types": list(missed_types or []),
        "error_detail": str(error or ""),
    }


def extract_analysis_error_detail(evaluation: Mapping[str, Any] | None) -> str:
    if not isinstance(evaluation, Mapping):
        return ""
    return str(evaluation.get("error_detail") or "")

