import os
import sys
import unittest
from unittest.mock import patch

import server_runtime.launcher as launcher


class LauncherDefaultTests(unittest.TestCase):
    def test_main_uses_docker_socket_by_default(self):
        with patch.object(sys, "argv", ["run_server.py", "--foreground", "--no-open-admin"]), patch(
            "server_runtime.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server_runtime.launcher._print_security_warnings",
        ), patch(
            "server_runtime.launcher._run_docker_compose",
            return_value=0,
        ) as run_compose:
            result = launcher.main()

        self.assertEqual(result, 0)
        self.assertTrue(run_compose.call_args.kwargs["with_docker_socket"])
        self.assertEqual(run_compose.call_args.kwargs["compose_mode"], "dev")

    def test_main_disables_docker_socket_when_flag_is_set(self):
        with patch.object(
            sys,
            "argv",
            ["run_server.py", "--foreground", "--no-open-admin", "--without-docker-socket"],
        ), patch(
            "server_runtime.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server_runtime.launcher._print_security_warnings",
        ), patch(
            "server_runtime.launcher._run_docker_compose",
            return_value=0,
        ) as run_compose:
            result = launcher.main()

        self.assertEqual(result, 0)
        self.assertFalse(run_compose.call_args.kwargs["with_docker_socket"])
        self.assertEqual(run_compose.call_args.kwargs["compose_mode"], "dev")

    def test_main_supports_ops_compose_mode(self):
        with patch.object(
            sys,
            "argv",
            ["run_server.py", "--foreground", "--no-open-admin", "--compose-mode", "ops"],
        ), patch(
            "server_runtime.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server_runtime.launcher._print_security_warnings",
        ), patch(
            "server_runtime.launcher._run_docker_compose",
            return_value=0,
        ) as run_compose:
            result = launcher.main()

        self.assertEqual(result, 0)
        self.assertEqual(run_compose.call_args.kwargs["compose_mode"], "ops")

    def test_local_https_uses_https_bind_port_by_default(self):
        with patch.dict(os.environ, {"ENABLE_HTTPS": "true", "HTTPS_BIND_PORT": "8443"}, clear=False), patch.object(
            sys,
            "argv",
            ["run_server.py", "--local", "--no-open-admin"],
        ), patch(
            "server_runtime.launcher._run_local_runtime_server",
            return_value=0,
        ) as run_local:
            result = launcher.main()

        self.assertEqual(result, 0)
        self.assertEqual(run_local.call_args.kwargs["port"], 8443)

    def test_detached_https_compose_uses_https_health_and_admin_urls(self):
        ready_services = set(launcher.EXPECTED_DOCKER_SERVICES)
        with patch.dict(
            os.environ,
            {"ENABLE_HTTPS": "true", "HTTPS_PUBLIC_PORT": "443", "HTTP_REDIRECT_PORT": "8000"},
            clear=False,
        ), patch.object(
            sys,
            "argv",
            ["run_server.py"],
        ), patch(
            "server_runtime.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server_runtime.launcher._print_security_warnings",
        ), patch(
            "server_runtime.launcher._run_docker_compose",
            return_value=0,
        ), patch(
            "server_runtime.launcher._wait_for_services",
            return_value=(True, ready_services, {}),
        ), patch(
            "server_runtime.launcher._wait_for_url",
            return_value=True,
        ) as wait_for_url, patch(
            "server_runtime.launcher._wait_for_http_redirect",
            return_value=True,
        ) as wait_for_redirect, patch(
            "server_runtime.launcher._open_admin_panel",
        ) as open_admin:
            result = launcher.main()

        self.assertEqual(result, 0)
        wait_for_url.assert_called_once_with("https://127.0.0.1/health", 90, insecure_https=True)
        wait_for_redirect.assert_called_once_with(
            "http://127.0.0.1:8000/health",
            expected_prefix="https://127.0.0.1",
            timeout_seconds=90,
        )
        open_admin.assert_called_once_with("https://127.0.0.1/admin.html")


if __name__ == "__main__":
    unittest.main()
