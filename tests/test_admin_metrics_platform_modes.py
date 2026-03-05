from __future__ import annotations

import unittest

from backend.admin_metrics import AdminMetrics


class AdminMetricsPlatformModeTests(unittest.TestCase):
    def test_platform_mode_metrics_include_operations_and_dispatch(self) -> None:
        metrics = AdminMetrics(window_minutes=10, active_window_seconds=30)

        problem_token = metrics.start_platform_mode_call("auditor", "problem")
        metrics.end_platform_mode_call(problem_token, success=True)

        submit_token = metrics.start_platform_mode_call("auditor", "submit")
        metrics.end_platform_mode_call(submit_token, success=False)

        background_token = metrics.start_platform_mode_call("auditor", "submit_background")
        metrics.end_platform_mode_call(background_token, success=True)

        metrics.record_platform_mode_submit_dispatch("auditor", queued=True)
        metrics.record_platform_mode_submit_dispatch("auditor", queued=False)
        metrics.record_platform_mode_enqueue_failure("auditor")

        snapshot = metrics.snapshot()
        platform_modes = snapshot["platformModes"]
        auditor = platform_modes["modes"]["auditor"]

        self.assertEqual(platform_modes["inFlight"], 0)
        self.assertEqual(auditor["problem"]["calls"], 1)
        self.assertEqual(auditor["problem"]["success"], 1)
        self.assertEqual(auditor["problem"]["failure"], 0)
        self.assertEqual(auditor["submit"]["calls"], 1)
        self.assertEqual(auditor["submit"]["success"], 0)
        self.assertEqual(auditor["submit"]["failure"], 1)
        self.assertEqual(auditor["submitBackground"]["calls"], 1)
        self.assertEqual(auditor["submitBackground"]["success"], 1)
        self.assertEqual(auditor["submitBackground"]["failure"], 0)
        self.assertEqual(auditor["dispatch"]["queued"], 1)
        self.assertEqual(auditor["dispatch"]["inline"], 1)
        self.assertEqual(auditor["dispatch"]["enqueueFailure"], 1)
        self.assertGreaterEqual(auditor["problem"]["avgLatencyMs"], 0.0)
        self.assertGreaterEqual(auditor["submit"]["avgLatencyMs"], 0.0)
        self.assertGreaterEqual(auditor["submitBackground"]["avgLatencyMs"], 0.0)

    def test_platform_mode_metrics_cover_all_new_modes(self) -> None:
        metrics = AdminMetrics(window_minutes=10, active_window_seconds=30)
        modes = ("auditor", "context-inference", "refactoring-choice", "code-blame")

        for mode in modes:
            token = metrics.start_platform_mode_call(mode, "problem")
            metrics.end_platform_mode_call(token, success=True)
            metrics.record_platform_mode_submit_dispatch(mode, queued=False)

        snapshot = metrics.snapshot()
        mode_metrics = snapshot["platformModes"]["modes"]
        self.assertEqual(set(mode_metrics.keys()), set(modes))
        for mode in modes:
            self.assertEqual(mode_metrics[mode]["problem"]["calls"], 1)
            self.assertEqual(mode_metrics[mode]["problem"]["success"], 1)
            self.assertEqual(mode_metrics[mode]["dispatch"]["inline"], 1)


if __name__ == "__main__":
    unittest.main()
