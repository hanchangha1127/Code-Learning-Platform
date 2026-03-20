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


class _FakeHistoryCacheConnection:
    def __init__(self, *, exists: bool = True) -> None:
        self._exists = exists
        self.increments: list[tuple[str, int]] = []

    def exists(self, _key: str) -> bool:
        return self._exists

    def incrby(self, key: str, value: int) -> int:
        self.increments.append((key, value))
        return value


class PlatformPublicBridgeTests(unittest.TestCase):
    def test_load_runtime_history_forwards_limit_to_learning_service(self) -> None:
        payload = [{"problem_id": "hist-1"}]

        with patch.object(platform_public_bridge.learning_service, "user_history", return_value=payload) as mock_history:
            result = platform_public_bridge._load_runtime_history("bridge-user", limit=25)

        self.assertEqual(result, payload)
        mock_history.assert_called_once_with("bridge-user", limit=25)

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
            patch.object(
                platform_public_bridge,
                "_request_runtime_problem",
                return_value={"problemId": "code-block-7", "objective": "반복문 누적 흐름을 완성하세요."},
            ),
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
        self.assertEqual(payload["objective"], "반복문 누적 흐름을 완성하세요.")
        self.assertEqual(emitted_payloads, [payload])
        self.assertEqual(fake_db.commits, 0)
        self.assertEqual(fake_db.rollbacks, 0)
        mock_follow_up.assert_called_once()

    def test_defer_problem_follow_up_raises_when_local_queue_is_full(self) -> None:
        with (
            patch.object(platform_public_bridge, "is_rq_enabled", return_value=False),
            patch.object(platform_public_bridge._PROBLEM_FOLLOW_UP_SLOTS, "acquire", return_value=False),
            patch.object(platform_public_bridge, "_persist_problem") as mock_persist,
            patch.object(platform_public_bridge, "_record_ops_event_best_effort") as mock_record_event,
        ):
            with self.assertRaises(platform_public_bridge.ProblemFollowUpUnavailableError):
                platform_public_bridge._defer_problem_follow_up(
                    mode="analysis",
                    username="bridge-user",
                    user_id=7,
                    problem_payload={"problemId": "analysis-9"},
                    runtime_payload={"problemId": "analysis-9"},
                    event_type="problem_requested",
                    latency_ms=120,
                    language="python",
                    difficulty="beginner",
                )

        mock_persist.assert_not_called()
        mock_record_event.assert_not_called()

    def test_defer_problem_follow_up_uses_rq_enqueue_when_enabled(self) -> None:
        with (
            patch.object(platform_public_bridge, "is_rq_enabled", return_value=True),
            patch.object(platform_public_bridge, "enqueue_problem_follow_up_job") as mock_enqueue,
            patch.object(platform_public_bridge._PROBLEM_FOLLOW_UP_SLOTS, "acquire") as mock_acquire,
        ):
            platform_public_bridge._defer_problem_follow_up(
                mode="analysis",
                username="bridge-user",
                user_id=7,
                problem_payload={"problemId": "analysis-10"},
                runtime_payload={"problemId": "analysis-10"},
                event_type="problem_requested",
                latency_ms=120,
                language="python",
                difficulty="beginner",
            )

        mock_enqueue.assert_called_once()
        mock_acquire.assert_not_called()

    def test_defer_problem_follow_up_raises_when_rq_enqueue_fails(self) -> None:
        with (
            patch.object(platform_public_bridge, "is_rq_enabled", return_value=True),
            patch.object(platform_public_bridge, "enqueue_problem_follow_up_job", side_effect=RuntimeError("rq down")),
        ):
            with self.assertRaises(platform_public_bridge.ProblemFollowUpUnavailableError):
                platform_public_bridge._defer_problem_follow_up(
                    mode="analysis",
                    username="bridge-user",
                    user_id=7,
                    problem_payload={"problemId": "analysis-11"},
                    runtime_payload={"problemId": "analysis-11"},
                    event_type="problem_requested",
                    latency_ms=120,
                    language="python",
                    difficulty="beginner",
                )

    def test_request_mode_problem_normalizes_non_analysis_payload_for_persistence(self) -> None:
        fake_db = FakeSqlSession()

        with (
            patch.object(platform_public_bridge, "_request_runtime_problem", return_value={"problemId": "auditor-1", "title": "Audit me"}),
            patch.object(platform_public_bridge, "_persist_problem") as mock_persist,
            patch.object(platform_public_bridge, "_record_ops_event_best_effort"),
        ):
            payload = platform_public_bridge.request_mode_problem(
                mode="auditor",
                username="bridge-user",
                user_id=1,
                language="python",
                difficulty="beginner",
                db=fake_db,
            )

        self.assertEqual(payload["problemId"], "auditor-1")
        self.assertEqual(payload["mode"], "auditor")
        persisted_payload = mock_persist.call_args.kwargs["problem_payload"]
        self.assertEqual(persisted_payload["mode"], "auditor")
        self.assertEqual(persisted_payload["language"], "python")
        self.assertEqual(persisted_payload["difficulty"], "beginner")
        self.assertEqual(fake_db.commits, 1)
        self.assertEqual(fake_db.rollbacks, 0)

    def test_submit_mode_answer_keeps_success_when_ops_event_recording_fails(self) -> None:
        fake_db = FakeSqlSession()

        with (
            patch.object(platform_public_bridge, "_submit_runtime_answer", return_value={"correct": True, "score": 100}),
            patch.object(platform_public_bridge, "_persist_submission"),
            patch.object(platform_public_bridge, "_increment_public_history_total"),
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

    def test_submit_mode_answer_increments_cached_history_total_on_success(self) -> None:
        fake_db = FakeSqlSession()

        with (
            patch.object(platform_public_bridge, "_submit_runtime_answer", return_value={"correct": True, "score": 100}),
            patch.object(platform_public_bridge, "_persist_submission"),
            patch.object(platform_public_bridge, "_increment_public_history_total") as mock_increment,
            patch.object(platform_public_bridge, "_record_ops_event_best_effort"),
        ):
            payload = platform_public_bridge.submit_mode_answer(
                mode="code-block",
                username="bridge-user",
                user_id=1,
                body={"problemId": "code-block-1", "selectedOption": 1},
                db=fake_db,
            )

        self.assertEqual(payload["correct"], True)
        mock_increment.assert_called_once_with("bridge-user")

    def test_submit_mode_answer_rejects_deleted_modes(self) -> None:
        fake_db = FakeSqlSession()

        with self.assertRaisesRegex(ValueError, "unsupported mode"):
            platform_public_bridge.submit_mode_answer(
                mode="context-inference",
                username="bridge-user",
                user_id=1,
                body={"problemId": "cinfer-1", "report": "context report"},
                db=fake_db,
            )

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

    def test_history_mode_for_problem_uses_external_id_prefix_when_payload_mode_is_missing(self) -> None:
        problem = type(
            "Problem",
            (),
            {
                "kind": platform_public_bridge.ProblemKind.analysis,
                "external_id": "sfile:abc123",
            },
        )()

        mode = platform_public_bridge._history_mode_for_problem(
            problem=problem,
            problem_payload={},
            answer_payload={},
        )

        self.assertEqual(mode, "single-file-analysis")

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

    def test_history_problem_files_normalizes_advanced_analysis_payload(self) -> None:
        files = platform_public_bridge._history_problem_files(
            {
                "files": [
                    {
                        "id": "frontend",
                        "path": "frontend/page.tsx",
                        "name": "page.tsx",
                        "language": "tsx",
                        "role": "frontend",
                        "content": "export function Page() { return null; }\r\n",
                    },
                    {
                        "path": "backend/api.py",
                        "content": "def handler():\n    return None",
                    },
                ]
            },
            fallback_language="python",
        )

        self.assertEqual(len(files), 2)
        self.assertEqual(files[0]["id"], "frontend")
        self.assertEqual(files[0]["language"], "tsx")
        self.assertEqual(files[0]["role"], "frontend")
        self.assertEqual(files[0]["content"], "export function Page() { return null; }\n")
        self.assertEqual(files[1]["name"], "api.py")
        self.assertEqual(files[1]["language"], "python")
        self.assertEqual(files[1]["role"], "module")

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

    def test_get_public_history_forwards_limit_and_truncates_merged_rows(self) -> None:
        runtime_history = [
            {"problem_id": "runtime-1", "created_at": "2026-03-20T10:00:00+00:00"},
            {"problem_id": "runtime-2", "created_at": "2026-03-19T10:00:00+00:00"},
            {"problem_id": "runtime-3", "created_at": "2026-03-18T10:00:00+00:00"},
        ]
        db_history = [
            {"problem_id": "db-1", "created_at": "2026-03-17T10:00:00+00:00"},
            {"problem_id": "db-2", "created_at": "2026-03-16T10:00:00+00:00"},
        ]

        with (
            patch.object(platform_public_bridge.learning_service, "user_history", return_value=runtime_history) as mock_history,
            patch.object(platform_public_bridge, "_load_db_history", return_value=db_history) as mock_db_history,
        ):
            merged = platform_public_bridge.get_public_history("bridge-user", limit=2)

        mock_history.assert_called_once_with("bridge-user", limit=2)
        self.assertEqual(mock_db_history.call_args.kwargs["limit"], 2)
        self.assertEqual([item["problem_id"] for item in merged], ["runtime-1", "runtime-2"])

    def test_get_public_history_page_returns_metadata(self) -> None:
        history_rows = [{"problem_id": "runtime-1"}, {"problem_id": "runtime-2"}]

        with (
            patch.object(platform_public_bridge, "_load_public_history", return_value=(history_rows, 2)) as mock_history,
            patch.object(platform_public_bridge, "_get_public_history_total", return_value=5) as mock_total,
        ):
            payload = platform_public_bridge.get_public_history_page("bridge-user", limit=2)

        self.assertEqual(payload["history"], history_rows)
        self.assertEqual(payload["total"], 5)
        self.assertEqual(payload["hasMore"], True)
        self.assertEqual(payload["limit"], 2)
        mock_history.assert_called_once_with("bridge-user", limit=2)
        mock_total.assert_called_once_with("bridge-user")

    def test_get_public_history_total_uses_cache_before_seed(self) -> None:
        with (
            patch.object(platform_public_bridge, "_read_cached_public_history_total", return_value=7) as mock_read,
            patch.object(platform_public_bridge, "_seed_public_history_total") as mock_seed,
        ):
            total = platform_public_bridge._get_public_history_total("bridge-user")

        self.assertEqual(total, 7)
        mock_read.assert_called_once_with("bridge-user")
        mock_seed.assert_not_called()

    def test_increment_public_history_total_updates_existing_cache_entry(self) -> None:
        fake_conn = _FakeHistoryCacheConnection(exists=True)

        with (
            patch.object(platform_public_bridge, "_history_cache_connection", return_value=fake_conn),
            patch.object(platform_public_bridge, "_seed_public_history_total") as mock_seed,
        ):
            platform_public_bridge._increment_public_history_total("bridge-user", delta=2)

        self.assertEqual(
            fake_conn.increments,
            [(platform_public_bridge._history_total_cache_key("bridge-user"), 2)],
        )
        mock_seed.assert_not_called()

    def test_increment_public_history_total_seeds_when_cache_entry_is_missing(self) -> None:
        fake_conn = _FakeHistoryCacheConnection(exists=False)

        with (
            patch.object(platform_public_bridge, "_history_cache_connection", return_value=fake_conn),
            patch.object(platform_public_bridge, "_seed_public_history_total") as mock_seed,
        ):
            platform_public_bridge._increment_public_history_total("bridge-user")

        mock_seed.assert_called_once_with("bridge-user")

    def test_get_public_report_returns_latest_stored_report(self) -> None:
        payload = {"reportId": 77, "goal": "Stored report"}
        fake_db = object()

        with patch.object(platform_public_bridge, "_db_session") as mock_db_session, patch.object(
            platform_public_bridge,
            "get_latest_report_detail",
            return_value=payload,
        ):
            mock_db_session.return_value.__enter__.return_value = fake_db
            mock_db_session.return_value.__exit__.return_value = None

            result = platform_public_bridge.get_public_report("bridge-user", 1, fake_db)

        self.assertEqual(result, payload)

    def test_defer_problem_follow_up_runs_inline_when_executor_is_unavailable(self) -> None:
        with (
            patch.object(platform_public_bridge, "is_rq_enabled", return_value=False),
            patch.object(platform_public_bridge._PROBLEM_FOLLOW_UP_SLOTS, "acquire", return_value=True),
            patch.object(platform_public_bridge._PROBLEM_FOLLOW_UP_EXECUTOR, "submit", side_effect=RuntimeError("offline")),
            patch.object(platform_public_bridge._PROBLEM_FOLLOW_UP_SLOTS, "release") as mock_release,
            patch.object(platform_public_bridge, "_persist_problem") as mock_persist,
            patch.object(platform_public_bridge, "_record_ops_event_best_effort") as mock_record_event,
        ):
            platform_public_bridge._defer_problem_follow_up(
                mode="analysis",
                username="bridge-user",
                user_id=1,
                problem_payload={"problemId": "analysis-1"},
                runtime_payload={"problemId": "analysis-1"},
                event_type="problem_requested",
                latency_ms=10,
                language="python",
                difficulty="beginner",
            )

        mock_persist.assert_called_once()
        mock_record_event.assert_called_once()
        mock_release.assert_called_once()

    def test_request_mode_problem_does_not_emit_payload_when_follow_up_reservation_fails(self) -> None:
        emitted_payloads: list[dict] = []

        with (
            patch.object(
                platform_public_bridge,
                "_request_runtime_problem",
                return_value={"problemId": "analysis-13", "title": "reserved"},
            ),
            patch.object(
                platform_public_bridge,
                "_defer_problem_follow_up",
                side_effect=platform_public_bridge.ProblemFollowUpUnavailableError("stream_capacity_exceeded"),
            ),
            patch.object(platform_public_bridge, "_defer_failure_ops_event") as mock_failure_event,
        ):
            with self.assertRaises(platform_public_bridge.ProblemFollowUpUnavailableError):
                platform_public_bridge.request_mode_problem(
                    mode="analysis",
                    username="bridge-user",
                    user_id=1,
                    language="python",
                    difficulty="beginner",
                    db=None,
                    defer_persistence=True,
                    on_payload_ready=emitted_payloads.append,
                )

        self.assertEqual(emitted_payloads, [])
        mock_failure_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
