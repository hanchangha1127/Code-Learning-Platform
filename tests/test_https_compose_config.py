from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent


class HttpsComposeConfigTests(unittest.TestCase):
    def test_base_compose_mounts_cert_directory_and_tls_env(self) -> None:
        content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn('${TLS_CERTS_DIR:-./certs}:/certs:ro', content)
        self.assertIn('ENABLE_HTTPS: "${ENABLE_HTTPS:-false}"', content)
        self.assertIn('HTTPS_BIND_PORT: "${HTTPS_BIND_PORT:-8443}"', content)
        self.assertIn('HTTPS_PUBLIC_PORT: "${HTTPS_PUBLIC_PORT:-443}"', content)
        self.assertIn('HTTP_REDIRECT_PORT: "${HTTP_REDIRECT_PORT:-8000}"', content)

    def test_dev_and_ops_compose_expose_http_and_https_ports(self) -> None:
        for name in ("docker-compose.dev.yml", "docker-compose.ops.yml"):
            with self.subTest(name=name):
                content = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn('- "80:8000"', content)
                self.assertIn('- "443:8443"', content)
                self.assertIn('- "8443:8443"', content)
                self.assertIn('- "8000:8000"', content)


if __name__ == "__main__":
    unittest.main()
