from __future__ import annotations

import re
from typing import Any

from server.features.learning.content import normalize_language_id

def _language_file_extension(language_id: str) -> str:
    normalized = normalize_language_id(language_id) or str(language_id or "").strip().lower()
    return {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "csharp": "cs",
        "go": "go",
        "rust": "rs",
        "php": "php",
        "golfscript": "gs",
    }.get(normalized, "txt")


def _fallback_code_for_language(language_id: str) -> str:
    normalized = normalize_language_id(language_id) or str(language_id or "").strip().lower()
    if normalized == "python":
        return "def analyze_me(value):\n    return value\n"
    if normalized == "javascript":
        return "export function analyzeMe(value) {\n  return value;\n}\n"
    if normalized == "typescript":
        return "export function analyzeMe(value: number): number {\n  return value;\n}\n"
    if normalized == "java":
        return "class Analyzer {\n    static int analyze(int value) {\n        return value;\n    }\n}\n"
    if normalized == "c":
        return "int analyze_me(int value) {\n    return value;\n}\n"
    if normalized == "cpp":
        return "int analyzeMe(int value) {\n    return value;\n}\n"
    if normalized == "csharp":
        return "public static class Analyzer {\n    public static int Analyze(int value) => value;\n}\n"
    if normalized == "go":
        return "func analyzeMe(value int) int {\n\treturn value\n}\n"
    if normalized == "rust":
        return "fn analyze_me(value: i32) -> i32 {\n    value\n}\n"
    if normalized == "php":
        return "<?php\nfunction analyzeMe($value) {\n    return $value;\n}\n"
    if normalized == "golfscript":
        return "1 2+\n"
    return "function analyzeMe(value) {\n  return value;\n}\n"


def _strip_comments(code: str, language_id: str) -> str:
    """Strip common comments from generated code snippets."""

    if not code:
        return ""

    normalized_language = normalize_language_id(language_id) or str(language_id or "").lower()
    line_comment_markers: tuple[str, ...] = ()
    block_comment: tuple[str, str] | None = None

    if normalized_language in {"python", "golfscript"}:
        line_comment_markers = ("#",)
    elif normalized_language in {"javascript", "typescript", "java", "c", "cpp", "csharp", "go", "rust"}:
        line_comment_markers = ("//",)
        block_comment = ("/*", "*/")
    elif normalized_language == "php":
        line_comment_markers = ("//", "#")
        block_comment = ("/*", "*/")

    index = 0
    output: list[str] = []
    in_block_comment = False
    in_string: str | None = None

    while index < len(code):
        if in_block_comment:
            if block_comment and code.startswith(block_comment[1], index):
                in_block_comment = False
                index += len(block_comment[1])
            else:
                index += 1
            continue

        if in_string:
            if in_string in {"'''", '"""'}:
                if code.startswith(in_string, index):
                    output.append(in_string)
                    index += 3
                    in_string = None
                else:
                    output.append(code[index])
                    index += 1
                continue

            char = code[index]
            output.append(char)
            if char == "\\" and index + 1 < len(code):
                output.append(code[index + 1])
                index += 2
                continue
            if char == in_string:
                in_string = None
            index += 1
            continue

        if normalized_language == "python":
            if code.startswith("'''", index):
                output.append("'''")
                in_string = "'''"
                index += 3
                continue
            if code.startswith('"""', index):
                output.append('"""')
                in_string = '"""'
                index += 3
                continue

        if block_comment and code.startswith(block_comment[0], index):
            in_block_comment = True
            index += len(block_comment[0])
            continue

        skipped_line_comment = False
        for marker in line_comment_markers:
            if code.startswith(marker, index):
                while index < len(code) and code[index] not in "\n\r":
                    index += 1
                skipped_line_comment = True
                break
        if skipped_line_comment:
            continue

        char = code[index]
        if char in {"'", '"', "`"}:
            if char == "`" and normalized_language in {"python", "golfscript"}:
                output.append(char)
                index += 1
                continue
            in_string = char
            output.append(char)
            index += 1
            continue

        output.append(char)
        index += 1

    cleaned_lines = [line.rstrip() for line in "".join(output).splitlines()]
    return "\n".join(cleaned_lines).strip()


_ANALYSIS_OUTPUT_ONLY_PATTERNS: tuple[str, ...] = (
    "무엇이 출력",
    "무엇을 출력",
    "출력하는 값",
    "출력 값을",
    "출력값은",
    "최종 출력",
    "실행 결과는",
    "실행 결과를",
    "결과값은",
    "반환되는 값",
    "무엇을 반환",
    "반환값은",
    "return 값",
    "return value",
    "stdout",
    "콘솔에 찍히",
    "한 줄로 답",
)

_ANALYSIS_REASONING_TERMS: tuple[str, ...] = (
    "실행 흐름",
    "흐름",
    "단계",
    "순서",
    "변수",
    "상태",
    "조건",
    "분기",
    "반복",
    "이유",
    "의도",
    "근거",
    "역할",
)

_ANALYSIS_REASONING_FALLBACK_PROMPT = (
    "코드를 위에서 아래로 따라가며 실행 흐름을 단계별로 설명하고, 변수 상태 변화, 조건 분기, "
    "각 코드 조각의 역할을 함께 정리하세요. 최종 출력값이나 반환값만 적지 말고 왜 그런 흐름이 "
    "생기는지도 서술하세요."
)

_ANALYSIS_REASONING_REFERENCE_PREFIX = (
    "해설 포인트: 최종 출력이나 반환값만 적는 대신, 실행 순서와 변수/조건의 변화가 왜 그런 결과로 "
    "이어지는지 함께 설명해야 합니다."
)


def _is_output_only_analysis_text(text: object) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if not any(pattern in normalized for pattern in _ANALYSIS_OUTPUT_ONLY_PATTERNS):
        return False
    return not any(term in normalized for term in _ANALYSIS_REASONING_TERMS)


def _normalize_analysis_prompt(prompt: object) -> str:
    text = str(prompt or "").strip()
    if not text:
        return _ANALYSIS_REASONING_FALLBACK_PROMPT
    if _is_output_only_analysis_text(text):
        return _ANALYSIS_REASONING_FALLBACK_PROMPT
    return text


def _normalize_analysis_reference(reference: object) -> str:
    text = str(reference or "").strip()
    if not text:
        return ""
    if not _is_output_only_analysis_text(text):
        return text
    return f"{_ANALYSIS_REASONING_REFERENCE_PREFIX}\n{text}"


_AUDITOR_TRAP_DEFAULTS: list[dict[str, str]] = [
    {"type": "logic_error", "description": "조건 분기/경계값 처리 오류"},
    {"type": "input_validation", "description": "입력 검증 누락"},
    {"type": "authorization_bypass", "description": "권한 확인 누락"},
    {"type": "injection_risk", "description": "문자열 결합 기반 주입 취약점"},
    {"type": "state_consistency", "description": "상태 갱신 순서 오류"},
]


def _normalize_auditor_trap_catalog(value: Any, trap_count: int) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for entry in value:
            if not isinstance(entry, dict):
                continue
            trap_type = str(entry.get("type") or "").strip().lower()
            description = str(entry.get("description") or entry.get("hint") or "").strip()
            if not trap_type or not description:
                continue
            cleaned.append({"type": trap_type, "description": description})

    # Deduplicate by trap type while preserving order.
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in cleaned:
        trap_type = row["type"]
        if trap_type in seen:
            continue
        seen.add(trap_type)
        deduped.append(row)

    for fallback in _AUDITOR_TRAP_DEFAULTS:
        if len(deduped) >= trap_count:
            break
        if fallback["type"] in seen:
            continue
        seen.add(fallback["type"])
        deduped.append(dict(fallback))

    if trap_count <= 0:
        return deduped
    return deduped[:trap_count]


_CONTEXT_INFERENCE_FACET_DEFAULTS: list[str] = [
    "input_shape",
    "state_transition",
    "side_effect",
    "data_consistency",
    "security_guard",
]


def _normalize_context_inference_facets(value: Any) -> list[str]:
    facets: list[str] = []
    if isinstance(value, list):
        for entry in value:
            facet = str(entry or "").strip().lower()
            if not facet:
                continue
            if facet in facets:
                continue
            facets.append(facet)
    if not facets:
        facets.extend(_CONTEXT_INFERENCE_FACET_DEFAULTS)
    return facets


_REFACTORING_CHOICE_FACET_TAXONOMY: tuple[str, ...] = (
    "performance",
    "memory",
    "readability",
    "maintainability",
    "security",
    "testability",
)


def _normalize_refactoring_choice_facets(value: Any) -> list[str]:
    expected = set(_REFACTORING_CHOICE_FACET_TAXONOMY)
    facets: list[str] = []
    if isinstance(value, list):
        for entry in value:
            facet = str(entry or "").strip().lower()
            if not facet or facet not in expected:
                continue
            if facet in facets:
                continue
            facets.append(facet)
    if len(facets) < 3:
        for fallback in _REFACTORING_CHOICE_FACET_TAXONOMY:
            if fallback in facets:
                continue
            facets.append(fallback)
            if len(facets) >= 3:
                break
    if len(facets) > 4:
        facets = facets[:4]
    return facets


def _normalize_refactoring_choice_options(value: Any) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for entry in value:
            if not isinstance(entry, dict):
                continue
            option_id = str(entry.get("option_id") or entry.get("optionId") or "").strip().upper()
            if option_id not in {"A", "B", "C"}:
                continue
            title = str(entry.get("title") or "").strip() or f"{option_id} Option"
            code = str(entry.get("code") or "").rstrip()
            cleaned.append({"optionId": option_id, "title": title, "code": code})

    by_id = {row["optionId"]: row for row in cleaned}
    normalized: list[dict[str, str]] = []
    for option_id in ("A", "B", "C"):
        row = by_id.get(option_id)
        if not row:
            row = {
                "optionId": option_id,
                "title": f"{option_id} Option",
                "code": "def solution():\n    pass",
            }
        normalized.append(row)
    return normalized


def _normalize_refactoring_choice_option_reviews(value: Any) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for entry in value:
            if not isinstance(entry, dict):
                continue
            option_id = str(entry.get("option_id") or entry.get("optionId") or "").strip().upper()
            if option_id not in {"A", "B", "C"}:
                continue
            summary = str(entry.get("summary") or "").strip()
            if not summary:
                continue
            cleaned.append({"optionId": option_id, "summary": summary})

    by_id = {row["optionId"]: row["summary"] for row in cleaned}
    normalized: list[dict[str, str]] = []
    for option_id in ("A", "B", "C"):
        summary = by_id.get(option_id) or f"{option_id} option trade-off summary unavailable."
        normalized.append({"optionId": option_id, "summary": summary})
    return normalized


_CODE_BLAME_FACET_TAXONOMY: tuple[str, ...] = (
    "log_correlation",
    "root_cause_diff",
    "failure_mechanism",
    "blast_radius",
    "fix_strategy",
    "verification",
)


def _normalize_code_blame_facets(value: Any) -> list[str]:
    allowed = set(_CODE_BLAME_FACET_TAXONOMY)
    facets: list[str] = []
    if isinstance(value, list):
        for entry in value:
            facet = str(entry or "").strip().lower()
            if not facet or facet not in allowed:
                continue
            if facet in facets:
                continue
            facets.append(facet)
    if len(facets) < 3:
        for fallback in _CODE_BLAME_FACET_TAXONOMY:
            if fallback in facets:
                continue
            facets.append(fallback)
            if len(facets) >= 3:
                break
    if len(facets) > 4:
        facets = facets[:4]
    return facets


def _normalize_code_blame_commits(value: Any, candidate_count: int) -> list[dict[str, str]]:
    option_ids = ("A", "B", "C", "D", "E")[: max(1, int(candidate_count or 1))]
    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for entry in value:
            if not isinstance(entry, dict):
                continue
            option_id = str(entry.get("option_id") or entry.get("optionId") or "").strip().upper()
            if option_id not in option_ids:
                continue
            title = str(entry.get("title") or "").strip() or f"Commit {option_id}"
            diff = str(entry.get("diff") or "").rstrip()
            cleaned.append({"optionId": option_id, "title": title, "diff": diff})

    by_id = {row["optionId"]: row for row in cleaned}
    normalized: list[dict[str, str]] = []
    for option_id in option_ids:
        row = by_id.get(option_id)
        if not row:
            row = {
                "optionId": option_id,
                "title": f"Commit {option_id}",
                "diff": "diff --git a/app.py b/app.py\n@@\n+pass",
            }
        normalized.append(row)
    return normalized


def _normalize_code_blame_option_ids(value: Any, allowed_option_ids: list[str]) -> list[str]:
    allowed = set(allowed_option_ids)
    rows: list[str] = []
    if isinstance(value, list):
        for entry in value:
            token = str(entry or "").strip().upper()
            if token not in allowed or token in rows:
                continue
            rows.append(token)
    return rows


def _normalize_code_blame_commit_reviews(value: Any, option_ids: list[str]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for entry in value:
            if not isinstance(entry, dict):
                continue
            option_id = str(entry.get("option_id") or entry.get("optionId") or "").strip().upper()
            if option_id not in option_ids:
                continue
            summary = str(entry.get("summary") or "").strip()
            if not summary:
                continue
            cleaned.append({"optionId": option_id, "summary": summary})

    by_id = {row["optionId"]: row["summary"] for row in cleaned}
    normalized: list[dict[str, str]] = []
    for option_id in option_ids:
        summary = by_id.get(option_id) or f"{option_id} 커밋의 위험도를 다시 점검하세요."
        normalized.append({"optionId": option_id, "summary": summary})
    return normalized


def _normalize_advanced_analysis_files(
    value: Any,
    *,
    min_count: int,
    max_count: int,
    default_language: str,
    default_role: str = "module",
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if isinstance(value, list):
        for index, entry in enumerate(value, start=1):
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or entry.get("name") or "").strip()
            name = str(entry.get("name") or "").strip()
            if not path and name:
                path = name
            if not name and path:
                name = path.split("/")[-1]
            if not path:
                extension = _language_file_extension(default_language)
                path = f"src/file_{index}.{extension}"
            if not name:
                name = path.split("/")[-1]

            language = str(entry.get("language") or default_language).strip().lower() or default_language
            role = str(entry.get("role") or default_role).strip() or default_role
            content = str(entry.get("content") or entry.get("code") or "").rstrip()
            if language in {"python", "javascript", "typescript", "java", "c", "cpp", "csharp", "go", "rust", "php", "golfscript"}:
                content = _strip_comments(content, language).rstrip()
            if not content:
                continue

            normalized.append(
                {
                    "path": path,
                    "name": name,
                    "language": language,
                    "role": role,
                    "content": content,
                }
            )

    capped = normalized[: max(1, int(max_count or 1))]
    if len(capped) >= max(1, int(min_count or 1)):
        return capped

    fallback_count = max(1, int(min_count or 1))
    fallback_files: list[dict[str, str]] = []
    extension = _language_file_extension(default_language)
    for index in range(fallback_count):
        path = f"src/fallback_{index + 1}.{extension}"
        fallback_files.append(
            {
                "path": path,
                "name": path.split("/")[-1],
                "language": default_language,
                "role": default_role,
                "content": _fallback_code_for_language(default_language),
            }
        )
    return fallback_files


def _normalize_code_block_objective(value: Any, *, fallback: str = "", correct_option: str = "") -> str:
    candidates = [
        str(value or "").strip(),
        str(fallback or "").strip(),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        normalized = re.sub(r"\s+", " ", candidate).strip()
        if correct_option:
            normalized = normalized.replace(correct_option, "핵심 로직").strip()
        if normalized and normalized != "코드 빈칸 채우기":
            return normalized

    return "코드가 완성하려는 동작을 먼저 읽고 빈칸의 역할을 추론해 보세요."
