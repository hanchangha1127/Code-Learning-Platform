"""In-memory admin metrics collection for request/user/AI activity."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any, Dict

from backend.config import get_settings


def _minute_epoch(ts: float) -> int:
    return int(ts // 60) * 60


def _minute_label(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds).strftime("%H:%M")


@dataclass(frozen=True)
class AICallToken:
    started_at: float
    provider: str
    operation: str


@dataclass(frozen=True)
class PlatformModeCallToken:
    started_at: float
    mode: str
    operation: str


class AdminMetrics:
    """Thread-safe in-memory metrics snapshots for the admin panel."""

    def __init__(self, window_minutes: int = 60, active_window_seconds: int = 300) -> None:
        self.window_minutes = max(window_minutes, 10)
        self.active_window_seconds = max(active_window_seconds, 30)

        self._lock = Lock()
        self._started_at = time.time()

        self._in_flight_requests = 0
        self._in_flight_ai = 0

        self._request_total = 0
        self._request_errors = 0

        self._ai_total = 0
        self._ai_success = 0
        self._ai_failure = 0
        self._ai_latency_total_ms = 0.0
        self._ai_latency_samples = 0

        self._request_timeline: dict[int, dict[str, float]] = {}
        self._user_timeline: dict[int, dict[str, float]] = {}
        self._ai_timeline: dict[int, dict[str, float]] = {}

        self._user_last_seen: dict[str, float] = {}
        self._client_last_seen: dict[str, float] = {}

        self._platform_mode_in_flight = 0
        self._platform_mode_totals: dict[str, dict[str, Any]] = {}

    def _new_platform_mode_operation_bucket(self) -> dict[str, float]:
        return {
            "calls": 0.0,
            "success": 0.0,
            "failure": 0.0,
            "latency_total_ms": 0.0,
            "latency_count": 0.0,
        }

    def _new_platform_mode_bucket(self) -> dict[str, Any]:
        return {
            "problem": self._new_platform_mode_operation_bucket(),
            "submit": self._new_platform_mode_operation_bucket(),
            "submit_background": self._new_platform_mode_operation_bucket(),
            "dispatch": {
                "queued": 0.0,
                "inline": 0.0,
                "enqueue_failure": 0.0,
            },
        }

    def _normalize_platform_mode(self, mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        return normalized or "unknown"

    def _normalize_platform_operation(self, operation: str) -> str:
        normalized = str(operation or "").strip().lower()
        if normalized in {"problem", "submit", "submit_background"}:
            return normalized
        return "submit"

    def _platform_mode_bucket(self, mode: str) -> dict[str, Any]:
        normalized_mode = self._normalize_platform_mode(mode)
        return self._platform_mode_totals.setdefault(normalized_mode, self._new_platform_mode_bucket())

    def record_request_start(self, path: str, client_id: str | None = None) -> None:
        if path.startswith("/static/"):
            return

        now = time.time()
        minute_key = _minute_epoch(now)

        with self._lock:
            self._in_flight_requests += 1
            self._request_total += 1

            req_bucket = self._request_timeline.setdefault(minute_key, {"total": 0.0, "errors": 0.0})
            req_bucket["total"] += 1

            if client_id:
                self._client_last_seen[client_id] = now

            self._prune_locked(now)
            self._snapshot_active_locked(minute_key)

    def record_request_end(self, status_code: int) -> None:
        now = time.time()
        minute_key = _minute_epoch(now)

        with self._lock:
            self._in_flight_requests = max(self._in_flight_requests - 1, 0)
            req_bucket = self._request_timeline.setdefault(minute_key, {"total": 0.0, "errors": 0.0})

            if status_code >= 500:
                self._request_errors += 1
                req_bucket["errors"] += 1

            self._prune_locked(now)

    def record_user_activity(self, username: str, client_id: str | None = None) -> None:
        if not username:
            return

        now = time.time()
        minute_key = _minute_epoch(now)

        with self._lock:
            self._user_last_seen[username] = now
            if client_id:
                self._client_last_seen[client_id] = now

            self._prune_locked(now)
            self._snapshot_active_locked(minute_key)

    def start_ai_call(self, provider: str = "google", operation: str = "unknown") -> AICallToken:
        now = time.time()
        minute_key = _minute_epoch(now)

        with self._lock:
            self._in_flight_ai += 1
            self._ai_total += 1
            ai_bucket = self._ai_timeline.setdefault(
                minute_key,
                {
                    "calls": 0.0,
                    "success": 0.0,
                    "failure": 0.0,
                    "latency_total_ms": 0.0,
                    "latency_count": 0.0,
                },
            )
            ai_bucket["calls"] += 1

            self._prune_locked(now)

        return AICallToken(started_at=time.perf_counter(), provider=provider, operation=operation)

    def end_ai_call(self, token: AICallToken, success: bool) -> None:
        now = time.time()
        minute_key = _minute_epoch(now)
        latency_ms = max((time.perf_counter() - token.started_at) * 1000.0, 0.0)

        with self._lock:
            self._in_flight_ai = max(self._in_flight_ai - 1, 0)

            ai_bucket = self._ai_timeline.setdefault(
                minute_key,
                {
                    "calls": 0.0,
                    "success": 0.0,
                    "failure": 0.0,
                    "latency_total_ms": 0.0,
                    "latency_count": 0.0,
                },
            )

            if success:
                self._ai_success += 1
                ai_bucket["success"] += 1
            else:
                self._ai_failure += 1
                ai_bucket["failure"] += 1

            self._ai_latency_total_ms += latency_ms
            self._ai_latency_samples += 1
            ai_bucket["latency_total_ms"] += latency_ms
            ai_bucket["latency_count"] += 1

            self._prune_locked(now)

    def start_platform_mode_call(self, mode: str, operation: str) -> PlatformModeCallToken:
        now = time.time()
        normalized_mode = self._normalize_platform_mode(mode)
        normalized_operation = self._normalize_platform_operation(operation)

        with self._lock:
            self._platform_mode_in_flight += 1
            mode_bucket = self._platform_mode_bucket(normalized_mode)
            op_bucket = mode_bucket[normalized_operation]
            op_bucket["calls"] += 1
            self._prune_locked(now)

        return PlatformModeCallToken(
            started_at=time.perf_counter(),
            mode=normalized_mode,
            operation=normalized_operation,
        )

    def end_platform_mode_call(self, token: PlatformModeCallToken, success: bool) -> None:
        now = time.time()
        latency_ms = max((time.perf_counter() - token.started_at) * 1000.0, 0.0)

        with self._lock:
            self._platform_mode_in_flight = max(self._platform_mode_in_flight - 1, 0)
            mode_bucket = self._platform_mode_bucket(token.mode)
            op_bucket = mode_bucket[self._normalize_platform_operation(token.operation)]

            if success:
                op_bucket["success"] += 1
            else:
                op_bucket["failure"] += 1

            op_bucket["latency_total_ms"] += latency_ms
            op_bucket["latency_count"] += 1
            self._prune_locked(now)

    def record_platform_mode_submit_dispatch(self, mode: str, *, queued: bool) -> None:
        now = time.time()
        with self._lock:
            mode_bucket = self._platform_mode_bucket(mode)
            dispatch_bucket = mode_bucket["dispatch"]
            if queued:
                dispatch_bucket["queued"] += 1
            else:
                dispatch_bucket["inline"] += 1
            self._prune_locked(now)

    def record_platform_mode_enqueue_failure(self, mode: str) -> None:
        now = time.time()
        with self._lock:
            mode_bucket = self._platform_mode_bucket(mode)
            mode_bucket["dispatch"]["enqueue_failure"] += 1
            self._prune_locked(now)

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._prune_locked(now)

            active_users = len(self._user_last_seen)
            active_clients = len(self._client_last_seen)

            request_keys = sorted(self._request_timeline.keys())
            user_keys = sorted(self._user_timeline.keys())
            ai_keys = sorted(self._ai_timeline.keys())

            request_labels = [_minute_label(key) for key in request_keys]
            user_labels = [_minute_label(key) for key in user_keys]
            ai_labels = [_minute_label(key) for key in ai_keys]

            completed_ai_calls = self._ai_success + self._ai_failure
            avg_latency = (
                round(self._ai_latency_total_ms / completed_ai_calls, 2)
                if completed_ai_calls
                else 0.0
            )
            success_rate = round((self._ai_success / self._ai_total) * 100.0, 1) if self._ai_total else 0.0

            platform_modes_snapshot: dict[str, Any] = {}
            for mode in sorted(self._platform_mode_totals.keys()):
                mode_bucket = self._platform_mode_totals[mode]

                def _op_snapshot(operation: str) -> dict[str, Any]:
                    op_bucket = mode_bucket[operation]
                    latency_count = max(op_bucket["latency_count"], 1.0)
                    return {
                        "calls": int(op_bucket["calls"]),
                        "success": int(op_bucket["success"]),
                        "failure": int(op_bucket["failure"]),
                        "avgLatencyMs": round(op_bucket["latency_total_ms"] / latency_count, 2)
                        if op_bucket["latency_count"] > 0
                        else 0.0,
                    }

                dispatch_bucket = mode_bucket["dispatch"]
                platform_modes_snapshot[mode] = {
                    "problem": _op_snapshot("problem"),
                    "submit": _op_snapshot("submit"),
                    "submitBackground": _op_snapshot("submit_background"),
                    "dispatch": {
                        "queued": int(dispatch_bucket["queued"]),
                        "inline": int(dispatch_bucket["inline"]),
                        "enqueueFailure": int(dispatch_bucket["enqueue_failure"]),
                    },
                }

            return {
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
                "uptimeSeconds": int(max(now - self._started_at, 0)),
                "inFlightRequests": self._in_flight_requests,
                "activeUsers": active_users,
                "activeClients": active_clients,
                "requestTotals": {
                    "total": self._request_total,
                    "errors": self._request_errors,
                    "errorRate": round((self._request_errors / self._request_total) * 100.0, 2)
                    if self._request_total
                    else 0.0,
                },
                "requestsTimeline": {
                    "labels": request_labels,
                    "calls": [int(self._request_timeline[key]["total"]) for key in request_keys],
                    "errors": [int(self._request_timeline[key]["errors"]) for key in request_keys],
                },
                "userTimeline": {
                    "labels": user_labels,
                    "activeUsers": [int(self._user_timeline[key]["active_users"]) for key in user_keys],
                    "activeClients": [int(self._user_timeline[key]["active_clients"]) for key in user_keys],
                },
                "ai": {
                    "inFlight": self._in_flight_ai,
                    "totals": {
                        "calls": self._ai_total,
                        "success": self._ai_success,
                        "failure": self._ai_failure,
                        "successRate": success_rate,
                        "avgLatencyMs": avg_latency,
                    },
                    "timeline": {
                        "labels": ai_labels,
                        "calls": [int(self._ai_timeline[key]["calls"]) for key in ai_keys],
                        "success": [int(self._ai_timeline[key]["success"]) for key in ai_keys],
                        "failure": [int(self._ai_timeline[key]["failure"]) for key in ai_keys],
                        "avgLatencyMs": [
                            round(
                                self._ai_timeline[key]["latency_total_ms"]
                                / max(self._ai_timeline[key]["latency_count"], 1.0),
                                2,
                            )
                            for key in ai_keys
                        ],
                    },
                },
                "platformModes": {
                    "inFlight": self._platform_mode_in_flight,
                    "modes": platform_modes_snapshot,
                },
            }

    def _snapshot_active_locked(self, minute_key: int) -> None:
        users_bucket = self._user_timeline.setdefault(
            minute_key,
            {
                "active_users": 0.0,
                "active_clients": 0.0,
            },
        )
        users_bucket["active_users"] = max(users_bucket["active_users"], float(len(self._user_last_seen)))
        users_bucket["active_clients"] = max(users_bucket["active_clients"], float(len(self._client_last_seen)))

    def _prune_locked(self, now: float) -> None:
        active_cutoff = now - self.active_window_seconds

        stale_users = [key for key, seen in self._user_last_seen.items() if seen < active_cutoff]
        for key in stale_users:
            del self._user_last_seen[key]

        stale_clients = [key for key, seen in self._client_last_seen.items() if seen < active_cutoff]
        for key in stale_clients:
            del self._client_last_seen[key]

        minute_cutoff = _minute_epoch(now - (self.window_minutes * 60))
        for store in (self._request_timeline, self._user_timeline, self._ai_timeline):
            stale_minutes = [key for key in store.keys() if key < minute_cutoff]
            for key in stale_minutes:
                del store[key]


_metrics_singleton: AdminMetrics | None = None
_metrics_lock = Lock()


def get_admin_metrics() -> AdminMetrics:
    global _metrics_singleton
    if _metrics_singleton is None:
        with _metrics_lock:
            if _metrics_singleton is None:
                settings = get_settings()
                _metrics_singleton = AdminMetrics(
                    window_minutes=settings.admin_metrics_window_minutes,
                    active_window_seconds=settings.admin_active_window_seconds,
                )
    return _metrics_singleton
