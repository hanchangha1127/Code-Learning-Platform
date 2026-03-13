from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.services import platform_public_bridge


class FakeSqlSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.added = []

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def query(self, *_args, **_kwargs):
        return self


class PlatformPublicBridgeTests(unittest.TestCase):
    def test_request_mode_problem_normalizes_analysis_payload_for_response_and_persistence(self) -> None:
        legacy_payload = {
            "problem": {
                "id": "analysis-1",
                "title": "Trace the loop",
                "code": "for i in range(3):\n    print(i)",
                "prompt": "코드가 출력하는 값을 설명하세요.",
                "mode": "practice",
                "difficulty": "beginner",
                "track": "algorithms",
                "language": "python",
            },
            "mode": "practice",
            "skillLevel": "beginner",
            "selectedDifficulty": "초급",
        }
        fake_db = FakeSqlSession()

        with (
            patch.object(platform_public_bridge, "_request_runtime_problem", return_value=legacy_payload),
            patch.object(platform_public_bridge, "_persist_problem") as mock_persist,
            patch.object(platform_public_bridge, "_record_ops_event_best_effort") as mock_record_event,
        ):
            payload = platform_public_bridge.request_mode_problem(
                mode="analysis",
                username="bridge-user",
                user_id=1,
                language="python",
                difficulty="beginner",
                db=fake_db,
            )

        self.assertEqual(payload["problemId"], "analysis-1")
        self.assertEqual(payload["mode"], "analysis")
        self.assertEqual(payload["problem"]["id"], "analysis-1")
        self.assertEqual(payload["problem"]["problemId"], "analysis-1")
        self.assertEqual(payload["skillLevel"], "beginner")
        persisted_payload = mock_persist.call_args.kwargs["problem_payload"]
        self.assertEqual(persisted_payload["problemId"], "analysis-1")
        self.assertEqual(persisted_payload["mode"], "analysis")
        self.assertNotIn("problem", persisted_payload)
        self.assertEqual(fake_db.commits, 1)
        self.assertEqual(fake_db.rollbacks, 0)
        mock_record_event.assert_called_once()

    def test_request_mode_problem_keeps_success_when_ops_event_recording_fails(self) -> None:
        fake_db = FakeSqlSession()

        with (
            patch.object(platform_public_bridge, "_request_runtime_problem", return_value={"problemId": "analysis-2"}),
            patch.object(platform_public_bridge, "_persist_problem"),
            patch.object(platform_public_bridge, "record_ops_event", side_effect=RuntimeError("ops down")),
            patch.object(platform_public_bridge.logger, "exception"),
        ):
            payload = platform_public_bridge.request_mode_problem(
                mode="analysis",
                username="bridge-user",
                user_id=1,
                language="python",
                difficulty="beginner",
                db=fake_db,
            )

        self.assertEqual(payload["problemId"], "analysis-2")
        self.assertEqual(fake_db.commits, 1)
        self.assertEqual(fake_db.rollbacks, 1)

    def test_request_mode_problem_rolls_back_business_transaction_on_persist_failure(self) -> None:
        fake_db = FakeSqlSession()

        with (
            patch.object(platform_public_bridge, "_request_runtime_problem", return_value={"problemId": "analysis-3"}),
            patch.object(platform_public_bridge, "_persist_problem", side_effect=RuntimeError("persist failed")),
            patch.object(platform_public_bridge, "_record_ops_event_best_effort"),
        ):
            with self.assertRaisesRegex(RuntimeError, "persist failed"):
                platform_public_bridge.request_mode_problem(
                    mode="analysis",
                    username="bridge-user",
                    user_id=1,
                    language="python",
                    difficulty="beginner",
                    db=fake_db,
                )

        self.assertEqual(fake_db.commits, 0)
        self.assertEqual(fake_db.rollbacks, 1)

    def test_submit_mode_answer_keeps_success_when_ops_event_recording_fails(self) -> None:
        fake_db = FakeSqlSession()

        with (
            patch.object(platform_public_bridge, "_submit_runtime_answer", return_value={"correct": True, "score": 100}),
            patch.object(platform_public_bridge, "_persist_submission"),
            patch.object(platform_public_bridge, "record_ops_event", side_effect=RuntimeError("ops down")),
            patch.object(platform_public_bridge.logger, "exception"),
        ):
            payload = platform_public_bridge.submit_mode_answer(
                mode="code-block",
                username="bridge-user",
                user_id=1,
                body={"problemId": "code-block-1", "selectedOption": 1},
                db=fake_db,
            )

        self.assertEqual(payload["correct"], True)
        self.assertEqual(fake_db.commits, 1)
        self.assertEqual(fake_db.rollbacks, 1)

    def test_latest_submission_analysis_prefers_newest_created_at_then_id(self) -> None:
        older = type("Analysis", (), {"id": 9, "created_at": datetime(2026, 3, 1, 9, 0, 0)})()
        newer = type("Analysis", (), {"id": 2, "created_at": datetime(2026, 3, 1, 10, 0, 0)})()
        same_time_low = type("Analysis", (), {"id": 3, "created_at": datetime(2026, 3, 2, 9, 0, 0)})()
        same_time_high = type("Analysis", (), {"id": 7, "created_at": datetime(2026, 3, 2, 9, 0, 0)})()

        self.assertIs(platform_public_bridge._latest_submission_analysis([newer, older]), newer)
        self.assertIs(
            platform_public_bridge._latest_submission_analysis([same_time_low, same_time_high]),
            same_time_high,
        )


if __name__ == "__main__":
    unittest.main()
