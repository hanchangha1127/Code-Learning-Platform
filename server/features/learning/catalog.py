from __future__ import annotations

from typing import Any

from server.db.models import Problem, ProblemKind

MODE_LABELS: dict[str, str] = {
    "analysis": "코드 분석",
    "code-block": "코드 블록",
    "code-arrange": "코드 배치",
    "auditor": "감사관 모드",
    "refactoring-choice": "최적의 선택",
    "code-blame": "범인 찾기",
    "single-file-analysis": "단일 파일 분석",
    "multi-file-analysis": "다중 파일 분석",
    "fullstack-analysis": "풀스택 코드 분석",
}

MODE_LINKS: dict[str, str] = {
    "analysis": "/analysis.html",
    "code-block": "/codeblock.html",
    "code-arrange": "/arrange.html",
    "auditor": "/auditor.html",
    "refactoring-choice": "/refactoring-choice.html",
    "code-blame": "/code-blame.html",
    "single-file-analysis": "/single-file-analysis.html",
    "multi-file-analysis": "/multi-file-analysis.html",
    "fullstack-analysis": "/fullstack-analysis.html",
}

ACTIVE_FOCUS_MODES: frozenset[str] = frozenset(MODE_LINKS)

WORKSPACE_MODE_MAP: dict[str, str] = {
    "single-file-analysis.workspace": "single-file-analysis",
    "multi-file-analysis.workspace": "multi-file-analysis",
    "fullstack-analysis.workspace": "fullstack-analysis",
}

EXTERNAL_ID_PREFIX_MODE_MAP: dict[str, str] = {
    "sfile": "single-file-analysis",
    "mfile": "multi-file-analysis",
    "fstack": "fullstack-analysis",
    "cinfer": "context-inference",
    "rchoice": "refactoring-choice",
    "cblame": "code-blame",
    "auditor": "auditor",
    "cerr": "code-error",
    "ccalc": "code-calc",
    "cblock": "code-block",
    "analysis": "analysis",
}

PROBLEM_KIND_MODE_MAP: dict[str, str] = {
    "analysis": "analysis",
    "code_block": "code-block",
    "code_arrange": "code-arrange",
    "code_calc": "code-calc",
    "code_error": "code-error",
    "auditor": "auditor",
    "context_inference": "context-inference",
    "refactoring_choice": "refactoring-choice",
    "code_blame": "code-blame",
}


def mode_from_problem_kind(kind: ProblemKind | str) -> str:
    value = kind.value if hasattr(kind, "value") else str(kind)
    return PROBLEM_KIND_MODE_MAP.get(value, "analysis")


def infer_mode_from_problem(
    *,
    problem: Problem,
    problem_payload: dict[str, Any],
    answer_payload: dict[str, Any] | None = None,
) -> str:
    for payload in (problem_payload, answer_payload or {}):
        raw_mode = str(payload.get("mode") or "").strip()
        if raw_mode:
            return raw_mode

    workspace = str(problem_payload.get("workspace") or "").strip().lower()
    workspace_mode = WORKSPACE_MODE_MAP.get(workspace)
    if workspace_mode:
        return workspace_mode

    external_id = str(problem.external_id or "").strip().lower()
    if external_id:
        prefix = external_id.split(":", 1)[0]
        inferred_mode = EXTERNAL_ID_PREFIX_MODE_MAP.get(prefix)
        if inferred_mode:
            return inferred_mode

    return mode_from_problem_kind(problem.kind)
