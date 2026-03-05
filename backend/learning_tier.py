from __future__ import annotations

from typing import Any, Callable, Dict, List


def recent_attempts(
    service: Any,
    storage: Any,
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    events = service._collect_attempt_events(storage)
    instances = service._instances_by_id(storage)
    attempts: List[Dict[str, Any]] = []

    for event in events:
        created_at = event.get("created_at")
        if not created_at:
            continue

        correct = event.get("correct")
        if isinstance(correct, bool):
            verdict = correct
        else:
            score = event.get("score")
            try:
                score = float(score) if score is not None else None
            except (TypeError, ValueError):
                score = None
            if score is None:
                continue
            verdict = score >= 70

        difficulty = event.get("difficulty")
        if not difficulty:
            problem_id = event.get("problem_id")
            if problem_id and problem_id in instances:
                difficulty = instances[problem_id].get("difficulty")

        attempts.append(
            {
                "created_at": created_at,
                "correct": verdict,
                "difficulty": difficulty,
                "mode": event.get("mode") or event.get("type"),
            }
        )

    attempts.sort(key=lambda item: item["created_at"], reverse=True)
    return attempts[:limit]


def update_tier_if_needed(
    service: Any,
    storage: Any,
    username: str,
    *,
    tier_review_window: int,
    tier_beginner_ratio_limit: float,
    utcnow: Callable[[], str],
) -> None:
    events = service._collect_attempt_events(storage)
    total_attempts = len([item for item in events if item.get("created_at")])
    if total_attempts < tier_review_window:
        return

    profile = storage.find_one(lambda item: item.get("type") == "profile") or {}
    last_reviewed = int(profile.get("tier_reviewed_attempts", 0) or 0)
    if total_attempts - last_reviewed < tier_review_window:
        return

    attempts = recent_attempts(service, storage, limit=tier_review_window)
    if len(attempts) < tier_review_window:
        return

    correct_count = sum(1 for item in attempts if item.get("correct") is True)
    accuracy = correct_count / max(len(attempts), 1)
    accuracy_pct = round(accuracy * 100, 1)

    difficulty_counts = {"beginner": 0, "intermediate": 0, "advanced": 0, "unknown": 0}
    for item in attempts:
        diff = item.get("difficulty") or "unknown"
        if diff in difficulty_counts:
            difficulty_counts[diff] += 1
        else:
            difficulty_counts["unknown"] += 1

    total_with_diff = sum(
        difficulty_counts[key] for key in ("beginner", "intermediate", "advanced")
    )
    beginner_ratio = difficulty_counts["beginner"] / total_with_diff if total_with_diff else 0.0

    lines = []
    for idx, item in enumerate(attempts, 1):
        diff_label = item.get("difficulty") or "unknown"
        verdict_label = "정답" if item.get("correct") else "오답"
        lines.append(f"{idx}. {diff_label} · {verdict_label} · {item.get('mode')}")
    summary = (
        f"정확도: {accuracy_pct}%\n"
        f"난이도 분포: beginner {difficulty_counts['beginner']}, "
        f"intermediate {difficulty_counts['intermediate']}, "
        f"advanced {difficulty_counts['advanced']}, unknown {difficulty_counts['unknown']}\n"
        f"초급 비율: {round(beginner_ratio * 100, 1)}%"
    )
    context = f"{summary}\n\n" + "\n".join(lines)

    current_tier = profile.get("skill_level", "beginner")
    ai_result = service.ai_client.evaluate_tier(context, current_tier)
    proposed = ai_result.get("tier", current_tier)
    reason = ai_result.get("reason", "")

    tier_rank = {"beginner": 0, "intermediate": 1, "advanced": 2}
    current_rank = tier_rank.get(current_tier, 0)
    proposed_rank = tier_rank.get(proposed, current_rank)

    if beginner_ratio >= tier_beginner_ratio_limit and proposed_rank > current_rank:
        proposed = current_tier
        reason = (reason + " (초급 문제 비중이 높아 승급은 보류됨)").strip()

    if not reason:
        reason = "최근 기록 기반 자동 판단"

    def mutator(profile_data: Dict[str, Any]) -> Dict[str, Any]:
        profile_data["skill_level"] = proposed
        profile_data["tier_updated_at"] = utcnow()
        profile_data["tier_accuracy"] = accuracy_pct
        profile_data["tier_attempts"] = len(attempts)
        profile_data["tier_reviewed_attempts"] = total_attempts
        profile_data["tier_reason"] = reason
        return profile_data

    service._update_profile(storage, username, mutator)

