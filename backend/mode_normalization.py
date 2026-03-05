from __future__ import annotations

import random
from typing import Any, Mapping, Sequence

from backend.mode_policies import (
    CODE_BLAME_CULPRIT_COUNT_WEIGHTS,
    CODE_BLAME_OPTION_IDS,
    CODE_BLAME_FACET_TAXONOMY,
    CONTEXT_INFERENCE_TYPE_WEIGHTS,
    REFACTORING_CHOICE_OPTION_IDS,
    REFACTORING_CHOICE_FACET_TAXONOMY,
)


def normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for entry in value:
        text = str(entry or "").strip()
        if not text or text in rows:
            continue
        rows.append(text)
    return rows


def normalize_trap_types(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for entry in value:
        if isinstance(entry, dict):
            token = str(entry.get("type") or "").strip().lower()
        else:
            token = str(entry or "").strip().lower()
        if not token or token in rows:
            continue
        rows.append(token)
    return rows


def select_context_inference_type(
    difficulty_id: str,
    *,
    weights_by_difficulty: Mapping[str, Mapping[str, int]] = CONTEXT_INFERENCE_TYPE_WEIGHTS,
    default_difficulty: str | None = "intermediate",
) -> str:
    weights = weights_by_difficulty.get(difficulty_id)
    if not weights:
        if default_difficulty is None:
            raise ValueError("unsupported_context_inference_difficulty")
        weights = weights_by_difficulty.get(default_difficulty)
        if not weights:
            raise ValueError("context_inference_weights_missing")

    options = list(weights.keys())
    return random.choices(options, weights=[weights[key] for key in options], k=1)[0]


def select_weighted_count(
    *,
    count_weights: Mapping[int, int] = CODE_BLAME_CULPRIT_COUNT_WEIGHTS,
) -> int:
    options = list(count_weights.keys())
    return int(random.choices(options, weights=[count_weights[key] for key in options], k=1)[0])


def normalize_option_id(
    value: Any,
    *,
    option_ids: Sequence[str] = REFACTORING_CHOICE_OPTION_IDS,
    fallback_option_id: str = "A",
) -> str:
    token = str(value or "").strip().upper()
    if token in option_ids:
        return token
    return fallback_option_id


def normalize_refactoring_choice_options(
    value: Any,
    *,
    option_ids: Sequence[str] = REFACTORING_CHOICE_OPTION_IDS,
    missing_title_template: str = "{option_id} option",
    missing_code: str = "def solution():\n    pass",
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for row in value:
            if not isinstance(row, dict):
                continue
            option_id = str(row.get("optionId") or row.get("option_id") or "").strip().upper()
            if option_id not in option_ids:
                continue
            title = str(row.get("title") or "").strip() or missing_title_template.format(option_id=option_id)
            code = str(row.get("code") or "").rstrip()
            cleaned.append({"optionId": option_id, "title": title, "code": code})

    by_id = {row["optionId"]: row for row in cleaned}
    normalized: list[dict[str, str]] = []
    for option_id in option_ids:
        row = by_id.get(option_id)
        if not row:
            row = {
                "optionId": option_id,
                "title": missing_title_template.format(option_id=option_id),
                "code": missing_code,
            }
        normalized.append(row)
    return normalized


def normalize_refactoring_choice_option_reviews(
    value: Any,
    *,
    option_ids: Sequence[str] = REFACTORING_CHOICE_OPTION_IDS,
    missing_summary_template: str = "{option_id} option summary is unavailable.",
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for row in value:
            if not isinstance(row, dict):
                continue
            option_id = str(row.get("optionId") or row.get("option_id") or "").strip().upper()
            if option_id not in option_ids:
                continue
            summary = str(row.get("summary") or "").strip()
            if not summary:
                continue
            cleaned.append({"optionId": option_id, "summary": summary})

    by_id = {row["optionId"]: row["summary"] for row in cleaned}
    normalized: list[dict[str, str]] = []
    for option_id in option_ids:
        summary = by_id.get(option_id) or missing_summary_template.format(option_id=option_id)
        normalized.append({"optionId": option_id, "summary": summary})
    return normalized


def normalize_facets(
    value: Any,
    *,
    taxonomy: Sequence[str] = REFACTORING_CHOICE_FACET_TAXONOMY,
    min_count: int = 3,
    max_count: int = 4,
) -> list[str]:
    allowed = set(taxonomy)
    rows: list[str] = []
    if isinstance(value, list):
        for item in value:
            token = str(item or "").strip().lower()
            if token not in allowed or token in rows:
                continue
            rows.append(token)

    if len(rows) < min_count:
        for fallback in taxonomy:
            if fallback in rows:
                continue
            rows.append(fallback)
            if len(rows) >= min_count:
                break

    if len(rows) > max_count:
        rows = rows[:max_count]

    return rows


def normalize_code_blame_commits(
    value: Any,
    *,
    candidate_count: int,
    option_ids: Sequence[str] = CODE_BLAME_OPTION_IDS,
    missing_title_template: str = "Commit {option_id}",
    missing_diff: str = "diff --git a/app.py b/app.py\n@@\n+pass",
) -> list[dict[str, str]]:
    scoped_option_ids = list(option_ids[: max(1, int(candidate_count or 1))])

    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for row in value:
            if not isinstance(row, dict):
                continue
            option_id = str(row.get("optionId") or row.get("option_id") or "").strip().upper()
            if option_id not in scoped_option_ids:
                continue
            title = str(row.get("title") or "").strip() or missing_title_template.format(option_id=option_id)
            diff = str(row.get("diff") or "").rstrip()
            cleaned.append({"optionId": option_id, "title": title, "diff": diff})

    by_id = {row["optionId"]: row for row in cleaned}
    normalized: list[dict[str, str]] = []
    for option_id in scoped_option_ids:
        row = by_id.get(option_id)
        if not row:
            row = {
                "optionId": option_id,
                "title": missing_title_template.format(option_id=option_id),
                "diff": missing_diff,
            }
        normalized.append(row)
    return normalized


def normalize_code_blame_option_ids(
    value: Any,
    *,
    allowed_ids: Sequence[str],
) -> list[str]:
    allowed = set(str(item or "").strip().upper() for item in allowed_ids if str(item or "").strip())
    rows: list[str] = []
    if isinstance(value, list):
        for entry in value:
            token = str(entry or "").strip().upper()
            if not token or token not in allowed or token in rows:
                continue
            rows.append(token)
    return rows


def normalize_code_blame_commit_reviews(
    value: Any,
    *,
    option_ids: Sequence[str],
    missing_summary_template: str = "{option_id} commit risk summary unavailable.",
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    if isinstance(value, list):
        for row in value:
            if not isinstance(row, dict):
                continue
            option_id = str(row.get("optionId") or row.get("option_id") or "").strip().upper()
            if option_id not in option_ids:
                continue
            summary = str(row.get("summary") or "").strip()
            if not summary:
                continue
            cleaned.append({"optionId": option_id, "summary": summary})

    by_id = {row["optionId"]: row["summary"] for row in cleaned}
    normalized: list[dict[str, str]] = []
    for option_id in option_ids:
        summary = by_id.get(option_id) or missing_summary_template.format(option_id=option_id)
        normalized.append({"optionId": option_id, "summary": summary})
    return normalized


def normalize_code_blame_facets(
    value: Any,
    *,
    taxonomy: Sequence[str] = CODE_BLAME_FACET_TAXONOMY,
    min_count: int = 3,
    max_count: int = 4,
) -> list[str]:
    return normalize_facets(
        value,
        taxonomy=taxonomy,
        min_count=min_count,
        max_count=max_count,
    )

