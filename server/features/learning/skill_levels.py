from __future__ import annotations

import math
import re
from typing import Any

MAX_SKILL_LEVEL = 10
DEFAULT_SKILL_LEVEL = "level1"

LEGACY_SKILL_LEVEL_MAP: dict[str, str] = {
    "beginner": "level1",
    "intermediate": "level5",
    "advanced": "level10",
}

_SKILL_LEVEL_PATTERN = re.compile(r"^(?:level|레벨)[\s_-]*(\d{1,2})$", re.IGNORECASE)


def clamp_skill_level(level: int) -> int:
    return max(1, min(int(level), MAX_SKILL_LEVEL))


def skill_level_id(level: int) -> str:
    return f"level{clamp_skill_level(level)}"


def skill_level_number(value: Any, default: int = 1) -> int:
    fallback = clamp_skill_level(default)

    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return clamp_skill_level(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return fallback
        return clamp_skill_level(int(value))

    text = str(value or "").strip().lower()
    if not text:
        return fallback

    text = LEGACY_SKILL_LEVEL_MAP.get(text, text)

    if text.isdigit():
        return clamp_skill_level(int(text))

    match = _SKILL_LEVEL_PATTERN.match(text)
    if match is not None:
        return clamp_skill_level(int(match.group(1)))

    return fallback


def normalize_skill_level(value: Any, default: str = DEFAULT_SKILL_LEVEL) -> str:
    default_level = skill_level_number(default, 1)
    return skill_level_id(skill_level_number(value, default_level))


def skill_level_label(value: Any, default: str = DEFAULT_SKILL_LEVEL) -> str:
    return f"레벨 {skill_level_number(value, skill_level_number(default, 1))}"


def score_to_skill_level(score: Any, default: str = DEFAULT_SKILL_LEVEL) -> str:
    try:
        normalized = float(score)
    except (TypeError, ValueError):
        return normalize_skill_level(default)

    normalized = max(0.0, min(normalized, 1.0))
    if normalized >= 1.0:
        return skill_level_id(MAX_SKILL_LEVEL)
    return skill_level_id(int(normalized * MAX_SKILL_LEVEL) + 1)
