import unittest
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


def _build_client(admin_key: str = "unit-test-admin-key") -> TestClient:
    app = FastAPI()
    register_admin_api(
        app=app,
        settings=SimpleNamespace(admin_panel_key=admin_key),
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
        ):
            response = client.get("/api/admin/metrics", headers={"X-Admin-Key": "unit-test-admin-key"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        shutdown = ((payload.get("admin") or {}).get("shutdown") or {})
        self.assertEqual(shutdown.get("supported"), False)
        self.assertEqual(shutdown.get("reason"), "docker_socket_not_mounted")
        self.assertEqual(shutdown.get("requires_socket_override"), True)
        self.assertIn("with-docker-socket", shutdown.get("detail", ""))

    def test_admin_key_regression_wrong_and_missing(self):
        client = _build_client()

        wrong_key_response = client.get("/api/admin/metrics", headers={"X-Admin-Key": "wrong-key"})
        self.assertEqual(wrong_key_response.status_code, 403)

        no_key_client = _build_client(admin_key="")
        missing_key_response = no_key_client.get("/api/admin/metrics", headers={"X-Admin-Key": "anything"})
        self.assertEqual(missing_key_response.status_code, 503)

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
            status_info = admin_api._docker_control_status()

        self.assertEqual(status_info.get("supported"), False)
        self.assertEqual(status_info.get("reason"), "shutdown_targets_incomplete")


if __name__ == "__main__":
    unittest.main()
