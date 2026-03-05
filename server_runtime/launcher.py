from __future__ import annotations

import argparse
import os
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


def _wait_for_http(url: str, timeout_seconds: int) -> bool:
    deadline = time.time() + max(timeout_seconds, 5)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
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


def _run_local_uvicorn(host: str, port: int, workers: int) -> int:
    import uvicorn

    uvicorn.run("run_server:app", host=host, port=port, workers=workers, reload=False)
    return 0


def _run_docker_compose(
    project_dir: Path,
    detach: bool,
    build: bool,
    with_docker_socket: bool = False,
) -> int:
    cmd = ["docker", "compose"]
    if with_docker_socket:
        override_file = project_dir / "docker-compose.docker-socket.yml"
        if not override_file.exists():
            print(
                "[launcher] docker socket override file is missing "
                f"({override_file}). Falling back to base compose config."
            )
        else:
            cmd.extend(
                [
                    "-f",
                    "docker-compose.yml",
                    "-f",
                    "docker-compose.docker-socket.yml",
                ]
            )
    cmd.append("up")
    if build:
        cmd.append("--build")
    if detach:
        cmd.append("-d")
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

    if with_docker_socket or _compose_has_docker_socket(project_dir):
        print(
            "[security] docker-compose mounts /var/run/docker.sock into api container. "
            "This grants host-level Docker control; avoid in production unless required."
        )


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
    parser.set_defaults(with_docker_socket=True)
    parser.add_argument(
        "--with-docker-socket",
        dest="with_docker_socket",
        action="store_true",
        help="Mount Docker socket into the API container (default) for admin-triggered full-stack shutdown.",
    )
    parser.add_argument(
        "--without-docker-socket",
        dest="with_docker_socket",
        action="store_false",
        help="Disable Docker socket mount for tighter isolation (admin stack shutdown will be unavailable).",
    )
    args, _ = parser.parse_known_args()

    project_dir = Path(__file__).resolve().parent.parent

    if not args.local and not _is_in_docker():
        _print_security_warnings(project_dir, args.with_docker_socket)

        detach = not args.foreground
        if args.detach:
            detach = True

        return_code = _run_docker_compose(
            project_dir=project_dir,
            detach=detach,
            build=not args.no_build,
            with_docker_socket=args.with_docker_socket,
        )
        if return_code != 0:
            return return_code

        if detach and not args.no_open_admin:
            env_file = project_dir / ".env"
            admin_key = (
                os.getenv("ADMIN_PANEL_KEY")
                or _load_env_value(env_file, "ADMIN_PANEL_KEY")
                or ""
            )
            health_url = f"http://{args.admin_host}:{args.admin_port}/health"
            _wait_for_http(health_url, args.wait_timeout)
            admin_url = f"http://{args.admin_host}:{args.admin_port}/admin.html"
            if not admin_key:
                print("Admin panel key is not configured. Set ADMIN_PANEL_KEY in .env before using admin APIs.")
            print(f"Admin panel: {admin_url}")
            _open_admin_panel(admin_url)

        return 0

    return _run_local_uvicorn(host=args.host, port=args.port, workers=args.workers)


if __name__ == "__main__":
    sys.exit(main())
