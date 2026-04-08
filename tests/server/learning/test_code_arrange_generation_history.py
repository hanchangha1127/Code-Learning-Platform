from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server.features.learning import service as learning_mode_handlers
from server.features.learning.service import LearningService


class _FakeStorage:
    def __init__(self, items=None):
        self.items = list(items or [])

    def filter(self, predicate):
        return [item for item in self.items if predicate(item)]

    def append(self, item):
        self.items.append(item)


class CodeArrangeHistoryContextTests(unittest.TestCase):
    def test_learning_service_builds_arrange_history_context(self):
        service = LearningService(storage_manager=SimpleNamespace())
        storage = _FakeStorage(
            [
                {
                    "type": "code_arrange_instance",
                    "problem_id": "arr-2",
                    "language": "python",
                    "difficulty": "intermediate",
                    "title": "Sliding Window Arrange",
                    "code": "def solve(nums):\n    left = 0\n    return left",
                    "created_at": "2026-03-19T12:00:00+00:00",
                },
                {
                    "type": "code_arrange_event",
                    "problem_id": "arr-2",
                    "correct": True,
                    "created_at": "2026-03-19T12:05:00+00:00",
                },
                {
                    "type": "code_arrange_instance",
                    "problem_id": "arr-1",
                    "language": "python",
                    "difficulty": "beginner",
                    "title": "Prefix Sum Arrange",
                    "code": "def prefix_sum(values):\n    total = 0\n    return total",
                    "created_at": "2026-03-18T12:00:00+00:00",
                },
                {
                    "type": "code_arrange_event",
                    "problem_id": "arr-1",
                    "correct": False,
                    "created_at": "2026-03-18T12:03:00+00:00",
                },
            ]
        )

        context = service._code_arrange_history_context(storage)

        self.assertIsNotNone(context)
        self.assertIn("python/intermediate - correct - Sliding Window Arrange", context)
        self.assertIn("python/beginner - wrong - Prefix Sum Arrange", context)
        self.assertIn("first line: def solve(nums):", context)


class RequestCodeArrangeProblemTests(unittest.TestCase):
    def test_request_code_arrange_problem_passes_history_context_to_generator(self):
        storage = _FakeStorage()

        class _FakeProblemGenerator:
            def __init__(self):
                self.calls = []

            def generate_sync(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(
                    title="Arrange Problem",
                    code="def solve(items):\n    return len(items)",
                )

        generator = _FakeProblemGenerator()

        service = SimpleNamespace(
            problem_generator=generator,
            _get_user_storage=lambda _username: storage,
            _code_arrange_history_context=Mock(return_value="recent arrange history"),
            _chunk_and_shuffle_code=lambda code: {
                "ordered": [{"id": "blk-1", "code": code}],
                "shuffled": [{"id": "blk-1", "code": code}],
            },
            _update_tier_if_needed=lambda *_args, **_kwargs: None,
        )

        with patch("server.features.learning.service.generate_token", return_value="carrange-test"):
            result = learning_mode_handlers.request_code_arrange_problem(
                service,
                username="tester",
                language_id="python",
                difficulty_id="beginner",
                default_track_id="algorithms",
                difficulty_choices={"beginner": {"generator": "beginner"}},
                utcnow=lambda: "2026-03-19T12:00:00+00:00",
            )

        service._code_arrange_history_context.assert_called_once_with(storage)
        self.assertEqual(generator.calls[0]["history_context"], "recent arrange history")
        self.assertEqual(result["problemId"], "carrange-test")
        self.assertEqual(result["title"], "Arrange Problem")
        self.assertEqual(storage.items[0]["type"], "code_arrange_instance")


if __name__ == "__main__":
    unittest.main()

