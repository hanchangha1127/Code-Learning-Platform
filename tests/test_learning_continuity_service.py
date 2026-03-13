from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.services import learning_continuity_service as svc


def _history_items(date_text: str, count: int) -> list[dict[str, str]]:
    return [
        {"created_at": f"{date_text}T09:{index:02d}:00", "correct": True}
        for index in range(count)
    ]


class LearningContinuityServiceTests(unittest.TestCase):
    def test_serialize_learning_goal_uses_daily_default_when_value_is_missing(self) -> None:
        goal = SimpleNamespace(
            daily_target_sessions=None,
            weekly_target_sessions=None,
            focus_modes=[],
            focus_topics=[],
            updated_at=None,
        )

        payload = svc.serialize_learning_goal(goal)

        self.assertEqual(payload["dailyTargetSessions"], 10)

    def test_serialize_learning_goal_keeps_existing_saved_value(self) -> None:
        goal = SimpleNamespace(
            daily_target_sessions=8,
            weekly_target_sessions=8,
            focus_modes=[],
            focus_topics=[],
            updated_at=None,
        )

        payload = svc.serialize_learning_goal(goal)

        self.assertEqual(payload["dailyTargetSessions"], 8)

    def test_streak_does_not_increase_until_today_goal_is_achieved(self) -> None:
        history = (
            _history_items("2026-03-04", 5)
            + _history_items("2026-03-05", 5)
            + _history_items("2026-03-06", 3)
        )

        with patch("app.services.learning_continuity_service.utcnow", return_value=datetime(2026, 3, 6, 10, 0, 0)):
            streak = svc._calculate_streak_days(history, 5)

        self.assertEqual(streak, 2)

    def test_streak_includes_today_after_daily_goal_is_achieved(self) -> None:
        history = (
            _history_items("2026-03-04", 5)
            + _history_items("2026-03-05", 5)
            + _history_items("2026-03-06", 5)
        )

        with patch("app.services.learning_continuity_service.utcnow", return_value=datetime(2026, 3, 6, 18, 0, 0)):
            streak = svc._calculate_streak_days(history, 5)

        self.assertEqual(streak, 3)

    def test_streak_resets_to_zero_when_yesterday_goal_was_missed(self) -> None:
        history = _history_items("2026-03-04", 5) + _history_items("2026-03-06", 2)

        with patch("app.services.learning_continuity_service.utcnow", return_value=datetime(2026, 3, 6, 11, 0, 0)):
            streak = svc._calculate_streak_days(history, 5)

        self.assertEqual(streak, 0)

    def test_daily_goal_counts_today_progress(self) -> None:
        history = _history_items("2026-03-05", 4) + _history_items("2026-03-06", 3)

        with patch("app.services.learning_continuity_service.utcnow", return_value=datetime(2026, 3, 6, 14, 0, 0)):
            daily_goal = svc._build_daily_goal(history, 5)

        self.assertEqual(
            daily_goal,
            {
                "date": "2026-03-06",
                "targetSessions": 5,
                "completedSessions": 3,
                "remainingSessions": 2,
                "progressPercent": 60.0,
                "achieved": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
