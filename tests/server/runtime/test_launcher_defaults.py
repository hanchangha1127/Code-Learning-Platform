import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server.launcher as launcher


class LauncherDefaultTests(unittest.TestCase):
    def test_compose_runtime_env_loads_required_secrets_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            secrets_dir = project_dir / ".secrets"
            secrets_dir.mkdir()
            (secrets_dir / "db_password.txt").write_text("db-from-file\n", encoding="utf-8")
            (secrets_dir / "jwt_secret.txt").write_text("jwt-from-file\n", encoding="utf-8")
            (project_dir / ".env").write_text(
                "\n".join(
                    [
                        "DB_PASSWORD=",
                        "DB_PASSWORD_FILE=.secrets/db_password.txt",
                        "JWT_SECRET=",
                        "JWT_SECRET_FILE=.secrets/jwt_secret.txt",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                compose_env = launcher._compose_runtime_env(project_dir)

        self.assertEqual(compose_env["DB_PASSWORD"], "db-from-file")
        self.assertEqual(compose_env["JWT_SECRET"], "jwt-from-file")

    def test_main_uses_docker_socket_by_default(self):
        with patch.object(sys, "argv", ["run_server.py", "--foreground", "--no-open-admin"]), patch(
            "server.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server.launcher._print_security_warnings",
        ), patch(
            "server.launcher._run_docker_compose",
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
            "server.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server.launcher._print_security_warnings",
        ), patch(
            "server.launcher._run_docker_compose",
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
            "server.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server.launcher._print_security_warnings",
        ), patch(
            "server.launcher._run_docker_compose",
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
            "server.launcher._run_local_runtime_server",
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
            "server.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server.launcher._print_security_warnings",
        ), patch(
            "server.launcher._run_docker_compose",
            return_value=0,
        ), patch(
            "server.launcher._wait_for_services",
            return_value=(True, ready_services, {}),
        ), patch(
            "server.launcher._wait_for_url",
            return_value=True,
        ) as wait_for_url, patch(
            "server.launcher._wait_for_http_redirect",
            return_value=True,
        ) as wait_for_redirect, patch(
            "server.launcher._open_admin_panel",
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

    def test_detached_compose_falls_back_to_http_when_https_is_unavailable(self):
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
            "server.launcher._is_in_docker",
            return_value=False,
        ), patch(
            "server.launcher._print_security_warnings",
        ), patch(
            "server.launcher._run_docker_compose",
            return_value=0,
        ), patch(
            "server.launcher._wait_for_services",
            return_value=(True, ready_services, {}),
        ), patch(
            "server.launcher._wait_for_url",
            side_effect=[False, True],
        ) as wait_for_url, patch(
            "server.launcher._wait_for_http_redirect",
            return_value=False,
        ) as wait_for_redirect, patch(
            "server.launcher._open_admin_panel",
        ) as open_admin:
            result = launcher.main()

        self.assertEqual(result, 0)
        self.assertEqual(
            wait_for_url.call_args_list[0].args,
            ("https://127.0.0.1/health", 90),
        )
        self.assertEqual(
            wait_for_url.call_args_list[0].kwargs,
            {"insecure_https": True},
        )
        self.assertEqual(
            wait_for_url.call_args_list[1].args,
            ("http://127.0.0.1:8000/health", 90),
        )
        self.assertEqual(
            wait_for_url.call_args_list[1].kwargs,
            {"insecure_https": False},
        )
        wait_for_redirect.assert_not_called()
        open_admin.assert_called_once_with("http://127.0.0.1:8000/admin.html")


if __name__ == "__main__":
    unittest.main()
