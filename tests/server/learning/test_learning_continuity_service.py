from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server.features.learning import continuity as svc


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

        with patch("server.features.learning.continuity.utcnow", return_value=datetime(2026, 3, 6, 10, 0, 0)):
            streak = svc._calculate_streak_days(history, 5)

        self.assertEqual(streak, 2)

    def test_streak_includes_today_after_daily_goal_is_achieved(self) -> None:
        history = (
            _history_items("2026-03-04", 5)
            + _history_items("2026-03-05", 5)
            + _history_items("2026-03-06", 5)
        )

        with patch("server.features.learning.continuity.utcnow", return_value=datetime(2026, 3, 6, 18, 0, 0)):
            streak = svc._calculate_streak_days(history, 5)

        self.assertEqual(streak, 3)

    def test_streak_resets_to_zero_when_yesterday_goal_was_missed(self) -> None:
        history = _history_items("2026-03-04", 5) + _history_items("2026-03-06", 2)

        with patch("server.features.learning.continuity.utcnow", return_value=datetime(2026, 3, 6, 11, 0, 0)):
            streak = svc._calculate_streak_days(history, 5)

        self.assertEqual(streak, 0)

    def test_daily_goal_counts_today_progress(self) -> None:
        history = _history_items("2026-03-05", 4) + _history_items("2026-03-06", 3)

        with patch("server.features.learning.continuity.utcnow", return_value=datetime(2026, 3, 6, 14, 0, 0)):
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

    def test_parse_history_datetime_normalizes_timezone_aware_value_to_naive_utc(self) -> None:
        parsed = svc._parse_history_datetime({"created_at": "2026-03-06T18:00:00+09:00"})

        self.assertEqual(parsed, datetime(2026, 3, 6, 9, 0, 0))
        self.assertIsNone(parsed.tzinfo)

    def test_build_weekly_report_card_accepts_timezone_aware_created_at(self) -> None:
        db = Mock()
        detail = {
            "reportId": 17,
            "createdAt": "2026-03-06T09:00:00+09:00",
            "goal": "Focus on logic errors",
            "solutionSummary": "Review branching logic daily.",
        }

        with patch("server.features.learning.continuity.get_latest_report_detail", return_value=detail):
            with patch(
                "server.features.learning.continuity.utcnow",
                return_value=datetime(2026, 3, 10, 0, 0, 0),
            ):
                payload = svc._build_weekly_report_card(db, 9)

        self.assertTrue(payload["available"])
        self.assertFalse(payload["stale"])
        self.assertEqual(payload["reportId"], 17)

    def test_is_report_stale_normalizes_timezone_aware_datetime(self) -> None:
        created_at = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)

        with patch("server.features.learning.continuity.utcnow", return_value=datetime(2026, 3, 9, 0, 0, 0)):
            self.assertTrue(svc._is_report_stale(svc._to_naive_utc(created_at)))

    def test_get_or_create_learning_goal_returns_existing_row_after_duplicate_insert_race(self) -> None:
        existing_goal = SimpleNamespace(user_id=56)
        db = Mock()
        db.get.side_effect = [None, existing_goal]
        db.commit.side_effect = svc.IntegrityError("insert into user_learning_goals", None, Exception("duplicate"))

        result = svc.get_or_create_learning_goal(db, 56)

        self.assertIs(result, existing_goal)
        db.add.assert_called_once()
        db.rollback.assert_called_once()
        db.refresh.assert_not_called()

    def test_serialize_learning_goal_keeps_advanced_focus_modes(self) -> None:
        goal = SimpleNamespace(
            daily_target_sessions=8,
            weekly_target_sessions=8,
            focus_modes=["single-file-analysis", "multi-file-analysis", "fullstack-analysis"],
            focus_topics=[],
            updated_at=None,
        )

        payload = svc.serialize_learning_goal(goal)

        self.assertEqual(
            payload["focusModes"],
            ["single-file-analysis", "multi-file-analysis", "fullstack-analysis"],
        )

    def test_serialize_learning_goal_filters_removed_focus_modes(self) -> None:
        goal = SimpleNamespace(
            daily_target_sessions=8,
            weekly_target_sessions=8,
            focus_modes=["analysis", "code-calc", "code-arrange"],
            focus_topics=[],
            updated_at=None,
        )

        payload = svc.serialize_learning_goal(goal)

        self.assertEqual(payload["focusModes"], ["analysis", "code-arrange"])

    def test_serialize_review_item_keeps_advanced_mode_links(self) -> None:
        item = SimpleNamespace(
            id=11,
            mode="single-file-analysis",
            title="Review advanced analysis",
            weakness_tag="logic_error",
            due_at=datetime(2026, 3, 20, 9, 0, 0),
            priority=80,
            source_problem_id="sfile:11",
        )

        payload = svc.serialize_review_item(item)

        self.assertEqual(payload["modeLabel"], "\ub2e8\uc77c \ud30c\uc77c \ubd84\uc11d")
        self.assertEqual(payload["actionLink"], "/single-file-analysis.html")
        self.assertEqual(payload["resumeLink"], "/single-file-analysis.html?resume_review=11")

    def test_mode_from_problem_uses_workspace_for_advanced_analysis(self) -> None:
        problem = SimpleNamespace(
            kind=SimpleNamespace(value="analysis"),
            external_id="prob-11",
            problem_payload={"workspace": "single-file-analysis.workspace"},
        )

        mode = svc._mode_from_problem(problem)

        self.assertEqual(mode, "single-file-analysis")

    def test_weekly_report_card_handles_timezone_aware_created_at(self) -> None:
        with (
            patch(
                "server.features.learning.continuity.get_latest_report_detail",
                return_value={
                    "reportId": 17,
                    "createdAt": "2026-03-01T09:00:00+09:00",
                    "goal": "Keep improving",
                    "solutionSummary": "Review queue first",
                },
            ),
            patch(
                "server.features.learning.continuity.utcnow",
                return_value=datetime(2026, 3, 6, 0, 0, 0),
            ),
        ):
            payload = svc._build_weekly_report_card(Mock(), user_id=7)

        self.assertTrue(payload["available"])
        self.assertFalse(payload["stale"])
        self.assertEqual(payload["reportId"], 17)


if __name__ == "__main__":
    unittest.main()

