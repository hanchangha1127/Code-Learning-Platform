from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

CLIENT_DIFFICULTIES: tuple[str, str, str] = ("beginner", "intermediate", "advanced")

# Client difficulty labels and platform difficulty enum values are fixed by API contract.
CLIENT_TO_PLATFORM_DIFFICULTY: Mapping[str, str] = MappingProxyType(
    {
        "beginner": "easy",
        "intermediate": "medium",
        "advanced": "hard",
    }
)

MODE_PASS_THRESHOLD: float = 70.0

AUDITOR_TRAP_COUNT_BY_DIFFICULTY: Mapping[str, int] = MappingProxyType(
    {
        "beginner": 1,
        "intermediate": 2,
        "advanced": 3,
    }
)

CONTEXT_INFERENCE_TYPE_WEIGHTS: Mapping[str, Mapping[str, int]] = MappingProxyType(
    {
        "beginner": MappingProxyType({"pre_condition": 70, "post_condition": 30}),
        "intermediate": MappingProxyType({"pre_condition": 50, "post_condition": 50}),
        "advanced": MappingProxyType({"pre_condition": 30, "post_condition": 70}),
    }
)

CONTEXT_INFERENCE_COMPLEXITY_PROFILE_BY_DIFFICULTY: Mapping[str, str] = MappingProxyType(
    {
        "beginner": "single_function_local_state",
        "intermediate": "service_plus_repository_side_effect",
        "advanced": "multi_stage_transaction_auth_concurrency",
    }
)

REFACTORING_CHOICE_OPTION_IDS: tuple[str, str, str] = ("A", "B", "C")
REFACTORING_CHOICE_FACET_TAXONOMY: tuple[str, ...] = (
    "performance",
    "memory",
    "readability",
    "maintainability",
    "security",
    "testability",
)

REFACTORING_CHOICE_CONSTRAINT_COUNT_BY_DIFFICULTY: Mapping[str, int] = MappingProxyType(
    {
        "beginner": 2,
        "intermediate": 3,
        "advanced": 4,
    }
)

REFACTORING_CHOICE_COMPLEXITY_PROFILE_BY_DIFFICULTY: Mapping[str, str] = MappingProxyType(
    {
        "beginner": "single_function_local_state",
        "intermediate": "service_repository_cache_side_effect",
        "advanced": "concurrency_auth_resource_constraint_chain",
    }
)

CODE_BLAME_OPTION_IDS: tuple[str, str, str, str, str] = ("A", "B", "C", "D", "E")
CODE_BLAME_FACET_TAXONOMY: tuple[str, ...] = (
    "log_correlation",
    "root_cause_diff",
    "failure_mechanism",
    "blast_radius",
    "fix_strategy",
    "verification",
)

CODE_BLAME_CANDIDATE_COUNT_BY_DIFFICULTY: Mapping[str, int] = MappingProxyType(
    {
        "beginner": 3,
        "intermediate": 4,
        "advanced": 5,
    }
)

CODE_BLAME_CULPRIT_COUNT_WEIGHTS: Mapping[int, int] = MappingProxyType(
    {
        1: 70,
        2: 30,
    }
)

