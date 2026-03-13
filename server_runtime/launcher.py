from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


WEAK_SECRET_VALUES = {
    "change-this-admin-key",
    "changeme",
    "admin",
    "password",
    "123456",
}

EXPECTED_DOCKER_SERVICES = ("mysql", "redis", "api", "worker")
COMPOSE_MODE_FILES = {
    "dev": "docker-compose.dev.yml",
    "ops": "docker-compose.ops.yml",
}


def _normalize_filesystem_path(path: Path) -> Path:
    raw = str(path)
    if os.name == "nt":
        unc_prefix = "\\\\?\\UNC\\"
        extended_prefix = "\\\\?\\"
        if raw.startswith(unc_prefix):
            return Path("\\\\" + raw[len(unc_prefix) :])
        if raw.startswith(extended_prefix):
            return Path(raw[len(extended_prefix) :])
    return path


def _load_env_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            env_key, env_value = line.split("=", 1)
            if env_key.strip() == key:
                return env_value.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _load_bool_env_value(env_path: Path, key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        raw = _load_env_value(env_path, key)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_int_env_value(env_path: Path, key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        raw = _load_env_value(env_path, key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _wait_for_url(url: str, timeout_seconds: int, *, insecure_https: bool = False) -> bool:
    deadline = time.time() + max(timeout_seconds, 5)
    context = None
    if insecure_https and url.lower().startswith("https://"):
        context = ssl._create_unverified_context()
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2, context=context) as response:
                if 200 <= response.status < 500:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None

    def http_error_301(self, req, fp, code, msg, headers):  # type: ignore[override]
        return fp

    def http_error_302(self, req, fp, code, msg, headers):  # type: ignore[override]
        return fp

    def http_error_303(self, req, fp, code, msg, headers):  # type: ignore[override]
        return fp

    def http_error_307(self, req, fp, code, msg, headers):  # type: ignore[override]
        return fp

    def http_error_308(self, req, fp, code, msg, headers):  # type: ignore[override]
        return fp


def _wait_for_http_redirect(url: str, expected_prefix: str, timeout_seconds: int) -> bool:
    deadline = time.time() + max(timeout_seconds, 5)
    opener = urllib.request.build_opener(_NoRedirectHandler())
    while time.time() < deadline:
        try:
            with opener.open(url, timeout=2) as response:
                location = response.headers.get("Location") or ""
                if response.status in {301, 302, 303, 307, 308} and location.startswith(expected_prefix):
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _open_admin_panel(url: str) -> None:
    try:
        webbrowser.open(url, new=2)
    except Exception:
        pass


def _is_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _run_local_runtime_server(host: str, port: int, workers: int) -> int:
    from server_runtime.runtime_server import run_application_server

    return run_application_server(host=host, port=port, workers=workers)


def _resolve_https_runtime(project_dir: Path, *, local: bool) -> dict[str, int | bool]:
    env_file = project_dir / ".env"
    https_enabled = _load_bool_env_value(env_file, "ENABLE_HTTPS", False)
    https_bind_port = _load_int_env_value(env_file, "HTTPS_BIND_PORT", 8443)
    https_public_port = _load_int_env_value(env_file, "HTTPS_PUBLIC_PORT", 8443 if local else 443)
    http_redirect_port = _load_int_env_value(env_file, "HTTP_REDIRECT_PORT", 8000)
    return {
        "enabled": https_enabled,
        "https_bind_port": https_bind_port,
        "https_public_port": https_public_port,
        "http_redirect_port": http_redirect_port,
    }


def _format_public_netloc(host: str, port: int, *, https_enabled: bool) -> str:
    scheme_default_port = 443 if https_enabled else 80
    if port == scheme_default_port:
        return host
    return f"{host}:{port}"


def _run_docker_compose(
    project_dir: Path,
    detach: bool,
    build: bool,
    compose_mode: str,
    with_docker_socket: bool = True,
    services: tuple[str, ...] | None = None,
) -> int:
    cmd = _compose_command(project_dir, compose_mode, with_docker_socket)
    cmd.append("up")
    if build:
        cmd.append("--build")
    if detach:
        cmd.append("-d")
    if services:
        cmd.extend(services)
    return subprocess.run(cmd, cwd=project_dir).returncode


def _is_weak_secret(value: str) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return True
    if normalized.lower() in WEAK_SECRET_VALUES:
        return True
    return False


def _compose_has_docker_socket(project_dir: Path) -> bool:
    compose_path = project_dir / "docker-compose.yml"
    if not compose_path.exists():
        return False
    try:
        content = compose_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "/var/run/docker.sock" in content


def _print_security_warnings(project_dir: Path, with_docker_socket: bool) -> None:
    env_file = project_dir / ".env"
    admin_key = os.getenv("ADMIN_PANEL_KEY") or _load_env_value(env_file, "ADMIN_PANEL_KEY") or ""

    if _is_weak_secret(admin_key):
        print(
            "[security] ADMIN_PANEL_KEY is missing or weak. "
            "Set a non-default random key in .env before exposing admin APIs."
        )

    if with_docker_socket:
        print(
            "[security] docker-compose mounts /var/run/docker.sock into api container. "
            "This grants host-level Docker control; avoid in production unless required."
        )


def _compose_files(project_dir: Path, compose_mode: str, with_docker_socket: bool) -> list[Path]:
    base_file = project_dir / "docker-compose.yml"
    mode_filename = COMPOSE_MODE_FILES.get(compose_mode)
    if mode_filename is None:
        raise ValueError(f"Unsupported compose mode: {compose_mode}")

    mode_file = project_dir / mode_filename
    missing = [path for path in (base_file, mode_file) if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Required compose files are missing: {missing_text}")

    files = [base_file, mode_file]
    if with_docker_socket:
        override_file = project_dir / "docker-compose.docker-socket.yml"
        if not override_file.exists():
            print(
                "[launcher] docker socket override file is missing "
                f"({override_file}). Falling back to compose files without socket mount."
            )
        else:
            files.append(override_file)
    return files


def _compose_command(project_dir: Path, compose_mode: str, with_docker_socket: bool) -> list[str]:
    cmd = ["docker", "compose"]
    for compose_file in _compose_files(project_dir, compose_mode, with_docker_socket):
        cmd.extend(["-f", compose_file.name])
    return cmd


def _read_compose_status(
    project_dir: Path,
    compose_mode: str,
    with_docker_socket: bool,
) -> dict[str, dict[str, str]]:
    cmd = _compose_command(project_dir, compose_mode, with_docker_socket) + ["ps", "--format", "json"]
    result = subprocess.run(
        cmd,
        cwd=project_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return {}

    status_map: dict[str, dict[str, str]] = {}
    output = result.stdout or ""
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        service = str(row.get("Service", "")).strip()
        if not service:
            continue
        status_map[service] = {
            "state": str(row.get("State", "")).strip().lower(),
            "health": str(row.get("Health", "")).strip().lower(),
            "status": str(row.get("Status", "")).strip().lower(),
        }
    return status_map


def _service_ready(service: str, status_map: dict[str, dict[str, str]]) -> bool:
    current = status_map.get(service)
    if not current:
        return False

    if current.get("state") != "running":
        return False

    if service in {"mysql", "redis"}:
        health = current.get("health", "")
        status = current.get("status", "")
        return health == "healthy" or "healthy" in status

    return True


def _wait_for_services(
    project_dir: Path,
    compose_mode: str,
    with_docker_socket: bool,
    timeout_seconds: int,
) -> tuple[bool, set[str], dict[str, dict[str, str]]]:
    expected = set(EXPECTED_DOCKER_SERVICES)
    deadline = time.time() + max(timeout_seconds, 15)
    last_status: dict[str, dict[str, str]] = {}

    while time.time() < deadline:
        status_map = _read_compose_status(project_dir, compose_mode, with_docker_socket)
        if status_map:
            last_status = status_map

        ready_services = {
            service
            for service in expected
            if _service_ready(service, status_map)
        }
        if ready_services == expected:
            return True, ready_services, status_map
        time.sleep(2)

    ready_services = {
        service
        for service in expected
        if _service_ready(service, last_status)
    }
    return ready_services == expected, ready_services, last_status


def _print_service_failure_diagnostics(
    project_dir: Path,
    compose_mode: str,
    with_docker_socket: bool,
    missing_services: set[str],
    status_map: dict[str, dict[str, str]],
) -> None:
    if not missing_services:
        return

    print(
        "[launcher] Service startup incomplete. Missing services: "
        f"{', '.join(sorted(missing_services))}"
    )
    for service in sorted(missing_services):
        current = status_map.get(service, {})
        state = current.get("state", "not-found")
        health = current.get("health", "n/a")
        print(f"[launcher] {service}: state={state}, health={health}")

    compose_cmd = _compose_command(project_dir, compose_mode, with_docker_socket)
    for service in sorted(missing_services):
        print(f"[launcher] Showing last logs for '{service}'...")
        subprocess.run(compose_cmd + ["logs", "--tail=80", service], cwd=project_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        add_help=True,
        description="Launcher mode: default starts Docker Compose in background and opens admin panel.",
    )
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--no-open-admin", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=90)
    parser.add_argument("--admin-host", default="127.0.0.1")
    parser.add_argument("--admin-port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0", help="Local uvicorn host.")
    parser.add_argument("--port", type=int, default=8000, help="Local uvicorn port.")
    parser.add_argument("--workers", type=int, default=16, help="Local uvicorn worker count.")
    parser.add_argument(
        "--compose-mode",
        choices=tuple(COMPOSE_MODE_FILES.keys()),
        default="dev",
        help="Docker Compose profile to launch when not using --local.",
    )
    parser.set_defaults(with_docker_socket=True)
    parser.add_argument(
        "--with-docker-socket",
        dest="with_docker_socket",
        action="store_true",
        help="Mount Docker socket into the API container for admin-triggered full-stack shutdown.",
    )
    parser.add_argument(
        "--without-docker-socket",
        dest="with_docker_socket",
        action="store_false",
        help="Disable Docker socket mount for tighter isolation (admin stack shutdown will be unavailable).",
    )
    args, _ = parser.parse_known_args()

    project_dir = _normalize_filesystem_path(Path(__file__).resolve().parent.parent)
    https_runtime = _resolve_https_runtime(project_dir, local=bool(args.local))

    if not args.local and not _is_in_docker():
        _print_security_warnings(project_dir, args.with_docker_socket)

        detach = not args.foreground
        if args.detach:
            detach = True

        return_code = _run_docker_compose(
            project_dir=project_dir,
            detach=detach,
            build=not args.no_build,
            compose_mode=args.compose_mode,
            with_docker_socket=args.with_docker_socket,
        )
        if return_code != 0:
            return return_code

        if detach:
            stack_ready, ready_services, status_map = _wait_for_services(
                project_dir=project_dir,
                compose_mode=args.compose_mode,
                with_docker_socket=args.with_docker_socket,
                timeout_seconds=args.wait_timeout,
            )
            missing_services = set(EXPECTED_DOCKER_SERVICES) - ready_services

            if not stack_ready:
                _print_service_failure_diagnostics(
                    project_dir=project_dir,
                    compose_mode=args.compose_mode,
                    with_docker_socket=args.with_docker_socket,
                    missing_services=missing_services,
                    status_map=status_map,
                )
                return 1

        if detach and not args.no_open_admin:
            env_file = project_dir / ".env"
            admin_key = (
                os.getenv("ADMIN_PANEL_KEY")
                or _load_env_value(env_file, "ADMIN_PANEL_KEY")
                or ""
            )
            admin_port = args.admin_port
            if https_runtime["enabled"] and admin_port == parser.get_default("admin_port"):
                admin_port = int(https_runtime["https_public_port"])

            scheme = "https" if https_runtime["enabled"] else "http"
            public_netloc = _format_public_netloc(args.admin_host, admin_port, https_enabled=bool(https_runtime["enabled"]))
            health_url = f"{scheme}://{public_netloc}/health"
            _wait_for_url(health_url, args.wait_timeout, insecure_https=bool(https_runtime["enabled"]))
            if https_runtime["enabled"]:
                redirect_port = int(https_runtime["http_redirect_port"])
                redirect_url = f"http://{args.admin_host}:{redirect_port}/health"
                _wait_for_http_redirect(
                    redirect_url,
                    expected_prefix=f"https://{public_netloc}",
                    timeout_seconds=args.wait_timeout,
                )
            admin_url = f"{scheme}://{public_netloc}/admin.html"
            if not admin_key:
                print("Admin panel key is not configured. Set ADMIN_PANEL_KEY in .env before using admin APIs.")
            print(f"Admin panel: {admin_url}")
            _open_admin_panel(admin_url)

        return 0

    local_port = args.port
    if https_runtime["enabled"] and local_port == parser.get_default("port"):
        local_port = int(https_runtime["https_bind_port"])
    return _run_local_runtime_server(host=args.host, port=local_port, workers=args.workers)


if __name__ == "__main__":
    sys.exit(main())
