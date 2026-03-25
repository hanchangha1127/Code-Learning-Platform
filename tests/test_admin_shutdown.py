import unittest
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

import server_runtime.admin_api as admin_api
from server_runtime.admin_api import register_admin_api


class _FakeMetrics:
    def snapshot(self) -> dict:
        return {
            "generatedAt": "2026-02-21T00:00:00",
            "activeUsers": 1,
            "activeClients": 1,
            "inFlightRequests": 0,
            "requestTotals": {"total": 1, "errors": 0, "errorRate": 0.0},
            "requestsTimeline": {"labels": [], "calls": [], "errors": []},
            "userTimeline": {"labels": [], "activeUsers": [], "activeClients": []},
            "ai": {
                "inFlight": 0,
                "totals": {"calls": 0, "success": 0, "failure": 0, "successRate": 0.0, "avgLatencyMs": 0.0},
                "timeline": {"labels": [], "calls": [], "success": [], "failure": [], "avgLatencyMs": []},
            },
        }


class _FakeContainer:
    def __init__(self, cid: str, name: str, labels: dict[str, str] | None = None) -> None:
        self.id = cid
        self.name = name
        self.labels = labels or {}


class _FakeContainerManager:
    def __init__(self, containers: list[_FakeContainer]) -> None:
        self._containers = containers

    def get(self, ref: str) -> _FakeContainer:
        for container in self._containers:
            if container.name == ref or container.id == ref or container.id.startswith(ref):
                return container
        raise RuntimeError("container not found")

    def list(self, all: bool = True, filters: dict | None = None) -> list[_FakeContainer]:
        _ = all
        if not filters:
            return list(self._containers)

        label_filter = filters.get("label") if isinstance(filters, dict) else None
        if not label_filter:
            return list(self._containers)

        if "=" in label_filter:
            key, value = label_filter.split("=", 1)
            return [c for c in self._containers if (c.labels or {}).get(key) == value]

        return [c for c in self._containers if label_filter in (c.labels or {})]


class _FakeDockerClient:
    def __init__(self, containers: list[_FakeContainer]) -> None:
        self.containers = _FakeContainerManager(containers)

    def ping(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeRedisPipeline:
    def __init__(self, redis):
        self._redis = redis
        self._ops: list[tuple[str, tuple]] = []

    def delete(self, *keys: str):
        self._ops.append(("delete", keys))
        return self

    def setex(self, key: str, ttl: int, value: str):
        self._ops.append(("setex", (key, ttl, value)))
        return self

    def execute(self):
        for command, args in self._ops:
            getattr(self._redis, command)(*args)
        self._ops.clear()
        return True


class _FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, int] = {}
        self._ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        next_value = int(self._values.get(key, 0)) + 1
        self._values[key] = next_value
        return next_value

    def expire(self, key: str, ttl: int) -> bool:
        if key not in self._values:
            return False
        self._ttls[key] = int(ttl)
        return True

    def ttl(self, key: str) -> int:
        return int(self._ttls.get(key, -2))

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(key in self._values or key in self._ttls)
            self._values.pop(key, None)
            self._ttls.pop(key, None)
        return removed

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self._values[key] = str(value)
        self._ttls[key] = int(ttl)
        return True

    def pipeline(self) -> _FakeRedisPipeline:
        return _FakeRedisPipeline(self)


def _build_client(
    admin_key: str = "unit-test-admin-key",
    *,
    enable_admin_shutdown: bool = True,
    admin_throttle_backend: str = "memory",
) -> TestClient:
    app = FastAPI()
    register_admin_api(
        app=app,
        settings=SimpleNamespace(
            admin_panel_key=admin_key,
            enable_admin_shutdown=enable_admin_shutdown,
            admin_throttle_backend=admin_throttle_backend,
        ),
        admin_metrics=_FakeMetrics(),
        admin_file=Path("frontend/admin.html"),
    )
    return TestClient(app)


class AdminShutdownTests(unittest.TestCase):
    def test_shutdown_returns_503_when_docker_control_unavailable(self):
        client = _build_client()
        with patch(
            "server_runtime.admin_api._docker_control_status",
            return_value={
                "supported": False,
                "reason": "docker_control_unavailable",
                "requires_socket_override": True,
                "detail": "Cannot access Docker daemon from the API container.",
            },
        ):
            response = client.post("/api/admin/shutdown", headers={"X-Admin-Key": "unit-test-admin-key"})

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        detail = payload.get("detail") or {}
        self.assertEqual(detail.get("code"), "docker_control_unavailable")
        self.assertTrue(detail.get("requires_socket_override"))
        self.assertIn("with-docker-socket", detail.get("detail", ""))

    def test_shutdown_returns_503_when_disabled_by_config(self):
        client = _build_client(enable_admin_shutdown=False)

        response = client.post("/api/admin/shutdown", headers={"X-Admin-Key": "unit-test-admin-key"})

        self.assertEqual(response.status_code, 503)
        detail = response.json().get("detail") or {}
        self.assertEqual(detail.get("code"), "disabled_by_config")
        self.assertIn("CODE_PLATFORM_ENABLE_ADMIN_SHUTDOWN=true", detail.get("detail", ""))

    def test_shutdown_accepted_when_docker_control_is_available(self):
        client = _build_client()
        with patch(
            "server_runtime.admin_api._docker_control_status",
            return_value={
                "supported": True,
                "reason": "ok",
                "requires_socket_override": False,
                "detail": "Docker control is available.",
            },
        ), patch("server_runtime.admin_api._shutdown_runtime_stack", return_value=True):
            response = client.post("/api/admin/shutdown", headers={"X-Admin-Key": "unit-test-admin-key"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "accepted")

    def test_shutdown_gate_releases_after_failed_shutdown_task(self):
        client = _build_client()
        with patch(
            "server_runtime.admin_api._docker_control_status",
            return_value={
                "supported": True,
                "reason": "ok",
                "requires_socket_override": False,
                "detail": "Docker control is available.",
            },
        ), patch(
            "server_runtime.admin_api._shutdown_runtime_stack",
            side_effect=[False, False],
        ):
            first = client.post("/api/admin/shutdown", headers={"X-Admin-Key": "unit-test-admin-key"})
            second = client.post("/api/admin/shutdown", headers={"X-Admin-Key": "unit-test-admin-key"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json().get("status"), "accepted")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get("status"), "accepted")

    def test_metrics_include_shutdown_capability_fields(self):
        client = _build_client()
        with patch(
            "server_runtime.admin_api._docker_control_status",
            return_value={
                "supported": False,
                "reason": "docker_socket_not_mounted",
                "requires_socket_override": True,
                "detail": "Docker socket is not mounted inside the API container.",
            },
        ), patch(
            "server_runtime.admin_api._collect_admin_platform_summaries",
            return_value=(
                {
                    "totals": 12,
                    "statusCounts": {"pending": 3, "approved": 8, "hidden": 1},
                    "topPromptVersions": [{"version": "analysis-v2", "count": 5}],
                    "recentPendingProblems": [{"id": 9, "title": "Trace loop"}],
                },
                {
                    "windowHours": 24,
                    "total": 7,
                    "statusCounts": {"success": 4, "failure": 2, "review_required": 1},
                    "topEventTypes": [{"eventType": "problem_requested", "count": 3}],
                    "modeSummary": [{"mode": "analysis", "total": 4, "failure": 1, "avgLatencyMs": 132.4}],
                    "latest": [{"id": 1, "eventType": "submission_processed"}],
                },
            ),
        ):
            response = client.get("/api/admin/metrics", headers={"X-Admin-Key": "unit-test-admin-key"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        shutdown = ((payload.get("admin") or {}).get("shutdown") or {})
        content_summary = ((payload.get("admin") or {}).get("contentSummary") or {})
        ops_events = ((payload.get("admin") or {}).get("opsEvents") or {})
        self.assertEqual(shutdown.get("supported"), False)
        self.assertEqual(shutdown.get("reason"), "docker_socket_not_mounted")
        self.assertEqual(shutdown.get("requires_socket_override"), True)
        self.assertIn("with-docker-socket", shutdown.get("detail", ""))
        self.assertEqual(content_summary.get("totals"), 12)
        self.assertEqual(content_summary.get("statusCounts", {}).get("pending"), 3)
        self.assertEqual(ops_events.get("total"), 7)
        self.assertEqual(ops_events.get("statusCounts", {}).get("failure"), 2)

    def test_admin_key_regression_wrong_and_missing(self):
        client = _build_client()

        wrong_key_response = client.get("/api/admin/metrics", headers={"X-Admin-Key": "wrong-key"})
        self.assertEqual(wrong_key_response.status_code, 403)

        no_key_client = _build_client(admin_key="")
        missing_key_response = no_key_client.get("/api/admin/metrics", headers={"X-Admin-Key": "anything"})
        self.assertEqual(missing_key_response.status_code, 503)

    def test_admin_metrics_accepts_base64_encoded_unicode_header(self):
        client = _build_client(admin_key="관리자-키")
        encoded = base64.urlsafe_b64encode("관리자-키".encode("utf-8")).decode("ascii").rstrip("=")

        response = client.get("/api/admin/metrics", headers={"X-Admin-Key-B64": encoded})

        self.assertEqual(response.status_code, 200)

    def test_correct_key_recovers_even_after_rate_limit(self):
        client = _build_client()

        # Trigger temporary rate-limit block with repeated invalid key attempts.
        final_invalid = None
        for _ in range(5):
            final_invalid = client.get("/api/admin/metrics", headers={"X-Admin-Key": "wrong-key"})

        self.assertIsNotNone(final_invalid)
        self.assertEqual(final_invalid.status_code, 429)

        # A valid key should immediately clear the block for this client.
        valid_response = client.get("/api/admin/metrics", headers={"X-Admin-Key": "unit-test-admin-key"})
        self.assertEqual(valid_response.status_code, 200)

    def test_admin_key_rate_limit_accumulates_across_rotating_user_agents(self):
        client = _build_client()
        responses = []
        for attempt in range(5):
            responses.append(
                client.get(
                    "/api/admin/metrics",
                    headers={
                        "X-Admin-Key": "wrong-key",
                        "User-Agent": f"pytest-agent-{attempt}",
                    },
                )
            )

        self.assertEqual([response.status_code for response in responses[:4]], [403, 403, 403, 403])
        self.assertEqual(responses[4].status_code, 429)

    def test_redis_admin_throttle_state_survives_guard_rebuild_and_clears_on_success(self):
        shared_redis = _FakeRedis()

        with patch("server_runtime.admin_api._get_admin_redis_connection", return_value=shared_redis):
            first_client = _build_client(admin_throttle_backend="redis")
            for _ in range(4):
                response = first_client.get("/api/admin/metrics", headers={"X-Admin-Key": "wrong-key"})
                self.assertEqual(response.status_code, 403)

            blocked = first_client.get("/api/admin/metrics", headers={"X-Admin-Key": "wrong-key"})
            self.assertEqual(blocked.status_code, 429)
            self.assertIn("Retry-After", blocked.headers)

            second_client = _build_client(admin_throttle_backend="redis")
            still_blocked = second_client.get("/api/admin/metrics", headers={"X-Admin-Key": "wrong-key"})
            self.assertEqual(still_blocked.status_code, 429)

            recovered = second_client.get(
                "/api/admin/metrics",
                headers={"X-Admin-Key": "unit-test-admin-key"},
            )
            self.assertEqual(recovered.status_code, 200)

            post_clear = second_client.get("/api/admin/metrics", headers={"X-Admin-Key": "wrong-key"})
            self.assertEqual(post_clear.status_code, 403)

    def test_resolve_current_container_uses_hints(self):
        container = _FakeContainer(
            cid="0123456789ab",
            name="code-platform-api",
            labels={"com.docker.compose.service": "api"},
        )
        fake_client = _FakeDockerClient([container])

        with patch("server_runtime.admin_api._self_container_hints", return_value=["0123456789ab"]):
            resolved = admin_api._resolve_current_container(fake_client)

        self.assertIs(resolved, container)

    def test_docker_control_status_marks_incomplete_targets_unavailable(self):
        api_container = _FakeContainer(
            cid="abc123abc123",
            name="code-platform-api",
            labels={
                "com.docker.compose.project": "code3",
                "com.docker.compose.service": "api",
                "com.docker.compose.depends_on": "mysql:service_healthy:false,redis:service_healthy:false",
            },
        )
        fake_client = _FakeDockerClient([api_container])
        fake_docker_module = SimpleNamespace(from_env=lambda: fake_client)
        fake_socket = SimpleNamespace(exists=lambda: True)

        with patch.dict(sys.modules, {"docker": fake_docker_module}), patch(
            "server_runtime.admin_api._is_in_docker",
            return_value=True,
        ), patch.object(admin_api, "DOCKER_SOCKET_PATH", fake_socket), patch(
            "server_runtime.admin_api._self_container_hints",
            return_value=["abc123abc123"],
        ):
            status_info = admin_api._docker_control_status(SimpleNamespace(enable_admin_shutdown=True))

        self.assertEqual(status_info.get("supported"), False)
        self.assertEqual(status_info.get("reason"), "shutdown_targets_incomplete")

    def test_docker_control_status_returns_disabled_without_opt_in(self):
        status_info = admin_api._docker_control_status(SimpleNamespace(enable_admin_shutdown=False))

        self.assertEqual(status_info.get("supported"), False)
        self.assertEqual(status_info.get("reason"), "disabled_by_config")

    def test_docker_control_status_disables_local_process_shutdown_even_when_opted_in(self):
        with patch("server_runtime.admin_api._is_in_docker", return_value=False):
            status_info = admin_api._docker_control_status(SimpleNamespace(enable_admin_shutdown=True))

        self.assertEqual(status_info.get("supported"), False)
        self.assertEqual(status_info.get("reason"), "local_process_disabled")

    def test_admin_client_id_prefers_forwarded_for_from_trusted_proxy(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"x-forwarded-for": "198.51.100.10, 127.0.0.1"},
        )

        self.assertEqual(admin_api._admin_client_id(request), "198.51.100.10")

    def test_admin_client_id_ignores_forwarded_for_from_untrusted_source(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="203.0.113.10"),
            headers={"x-forwarded-for": "198.51.100.10"},
        )

        self.assertEqual(admin_api._admin_client_id(request), "203.0.113.10")

    def test_admin_client_id_ignores_private_proxy_source_by_default(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="10.0.0.5"),
            headers={"x-forwarded-for": "198.51.100.10, 10.0.0.5"},
        )

        self.assertEqual(admin_api._admin_client_id(request), "10.0.0.5")

    def test_admin_client_id_uses_only_client_ip_for_rate_limit_bucket(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="203.0.113.10"),
            headers={"user-agent": "pytest-admin-agent"},
        )

        self.assertEqual(
            admin_api._admin_client_id(request),
            "203.0.113.10",
        )

    def test_admin_client_id_ignores_forwarded_for_from_private_non_loopback_source_by_default(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="10.0.0.9"),
            headers={"x-forwarded-for": "198.51.100.10, 10.0.0.9"},
        )

        self.assertEqual(admin_api._admin_client_id(request), "10.0.0.9")


if __name__ == "__main__":
    unittest.main()

