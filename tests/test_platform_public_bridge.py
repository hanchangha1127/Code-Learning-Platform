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

    def test_request_mode_problem_can_defer_persistence_after_payload_is_ready(self) -> None:
        fake_db = FakeSqlSession()
        emitted_payloads: list[dict] = []

        with (
            patch.object(platform_public_bridge, "_request_runtime_problem", return_value={"problemId": "code-block-7"}),
            patch.object(platform_public_bridge, "_defer_problem_follow_up") as mock_follow_up,
        ):
            payload = platform_public_bridge.request_mode_problem(
                mode="code-block",
                username="bridge-user",
                user_id=1,
                language="python",
                difficulty="beginner",
                db=fake_db,
                defer_persistence=True,
                on_payload_ready=emitted_payloads.append,
            )

        self.assertEqual(payload["problemId"], "code-block-7")
        self.assertEqual(emitted_payloads, [payload])
        self.assertEqual(fake_db.commits, 0)
        self.assertEqual(fake_db.rollbacks, 0)
        mock_follow_up.assert_called_once()

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

    def test_problem_starter_code_can_render_files_payload(self) -> None:
        payload = {
            "files": [
                {"path": "frontend/page.tsx", "content": "export function Page() { return null; }"},
                {"path": "backend/api.py", "content": "def handler():\n    return None"},
            ]
        }

        starter = platform_public_bridge._problem_starter_code(payload)

        self.assertIn("File: frontend/page.tsx", starter)
        self.assertIn("export function Page()", starter)
        self.assertIn("File: backend/api.py", starter)
        self.assertIn("def handler()", starter)

    def test_submit_runtime_answer_supports_advanced_analysis_modes(self) -> None:
        with patch.object(
            platform_public_bridge.learning_service,
            "submit_single_file_analysis_report",
            return_value={"correct": True, "score": 88.0},
        ) as mock_submit:
            result = platform_public_bridge._submit_runtime_answer(
                "single-file-analysis",
                username="bridge-user",
                body={"problemId": "sfa-1", "report": "analysis report"},
            )

        self.assertEqual(result["score"], 88.0)
        mock_submit.assert_called_once_with("bridge-user", "sfa-1", "analysis report")

    def test_submission_code_uses_report_for_advanced_analysis_modes(self) -> None:
        code = platform_public_bridge._submission_code(
            "fullstack-analysis",
            {"problemId": "fsa-1", "report": "trace the request flow"},
        )

        self.assertEqual(code, "trace the request flow")


if __name__ == "__main__":
    unittest.main()
