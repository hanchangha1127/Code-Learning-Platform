from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import config as backend_config
from server_runtime import runtime_server


class RedirectAppTests(unittest.TestCase):
    def test_http_redirect_preserves_path_and_query_on_default_https_port(self) -> None:
        client = TestClient(
            runtime_server.create_http_redirect_app(https_public_port=443),
            base_url="http://learning.example:8000",
        )

        response = client.get("/platform/report?view=weekly", follow_redirects=False)

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "https://learning.example/platform/report?view=weekly")

    def test_http_redirect_keeps_method_and_non_default_https_port(self) -> None:
        client = TestClient(
            runtime_server.create_http_redirect_app(https_public_port=8443),
            base_url="http://127.0.0.1:8000",
        )

        response = client.post("/health", follow_redirects=False)

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "https://127.0.0.1:8443/health")


class HttpsSettingsTests(unittest.TestCase):
    def test_validate_https_requires_existing_cert_and_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = backend_config.Settings(
                enable_https=True,
                tls_certs_dir=Path(tmpdir),
                https_bind_port=8443,
                https_public_port=443,
                http_redirect_port=8000,
            )

            with self.assertRaisesRegex(ValueError, "SSL cert file not found"):
                settings.validate_https_settings()

    def test_validate_https_accepts_default_cert_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = Path(tmpdir) / "fullchain.pem"
            key_path = Path(tmpdir) / "privkey.pem"
            cert_path.write_text("test-cert", encoding="utf-8")
            key_path.write_text("test-key", encoding="utf-8")

            settings = backend_config.Settings(
                enable_https=True,
                tls_certs_dir=Path(tmpdir),
                https_bind_port=8443,
                https_public_port=443,
                http_redirect_port=8000,
            )

            settings.validate_https_settings()
            self.assertEqual(settings.resolved_ssl_certfile, cert_path.resolve())
            self.assertEqual(settings.resolved_ssl_keyfile, key_path.resolve())


class RuntimeServerDispatchTests(unittest.TestCase):
    def test_run_application_server_keeps_http_mode_when_https_disabled(self) -> None:
        with (
            patch.object(runtime_server, "get_settings", return_value=backend_config.Settings(enable_https=False)),
            patch.object(runtime_server, "_run_plain_http_server", return_value=0) as plain_server,
            patch.object(runtime_server, "_run_https_server") as https_server,
        ):
            result = runtime_server.run_application_server(host="127.0.0.1", port=8000, workers=1)

        self.assertEqual(result, 0)
        plain_server.assert_called_once()
        https_server.assert_not_called()

    def test_run_application_server_uses_https_mode_when_enabled(self) -> None:
        with (
            patch.object(
                runtime_server,
                "get_settings",
                return_value=backend_config.Settings(
                    enable_https=True,
                    https_bind_port=8443,
                    https_public_port=443,
                    http_redirect_port=8000,
                ),
            ),
            patch.object(runtime_server, "_run_plain_http_server") as plain_server,
            patch.object(runtime_server, "_run_https_server", return_value=0) as https_server,
        ):
            result = runtime_server.run_application_server(host="127.0.0.1", port=8000, workers=1)

        self.assertEqual(result, 0)
        plain_server.assert_not_called()
        https_server.assert_called_once_with(host="127.0.0.1", port=8443, workers=1)


if __name__ == "__main__":
    unittest.main()
