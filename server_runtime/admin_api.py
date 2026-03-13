from __future__ import annotations

import base64
import hmac
import logging
import os
import string
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import Response

from server_runtime.template_renderer import render_template_response

DOCKER_SOCKET_PATH = Path("/var/run/docker.sock")
logger = logging.getLogger(__name__)


def _is_in_docker() -> bool:
    return Path("/.dockerenv").exists()


_HEX_CHARS = set(string.hexdigits.lower())


def _looks_like_container_id(value: str) -> bool:
    candidate = (value or "").strip().lower()
    if len(candidate) < 12 or len(candidate) > 64:
        return False
    return all(ch in _HEX_CHARS for ch in candidate)



def _read_container_id_from_cgroup() -> str:
    cgroup_path = Path("/proc/self/cgroup")
    if not cgroup_path.exists():
        return ""

    try:
        for raw_line in cgroup_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(":")
            if len(parts) != 3:
                continue
            for segment in reversed(parts[2].split("/")):
                segment = segment.strip()
                if not segment:
                    continue
                if segment.endswith(".scope"):
                    segment = segment[: -len(".scope")]
                if segment.startswith("docker-"):
                    segment = segment[len("docker-") :]
                if segment.startswith("cri-containerd-"):
                    segment = segment[len("cri-containerd-") :]
                if _looks_like_container_id(segment):
                    return segment
    except OSError:
        return ""

    return ""



def _self_container_hints() -> list[str]:
    hints: list[str] = []

    for env_name in ("HOSTNAME", "CONTAINER_ID"):
        value = (os.getenv(env_name) or "").strip()
        if value:
            hints.append(value)

    hostname_path = Path("/etc/hostname")
    if hostname_path.exists():
        try:
            value = hostname_path.read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        if value:
            hints.append(value)

    cgroup_id = _read_container_id_from_cgroup()
    if cgroup_id:
        hints.append(cgroup_id)

    seen: set[str] = set()
    unique_hints: list[str] = []
    for hint in hints:
        normalized = hint.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_hints.append(normalized)
    return unique_hints



def _is_stack_target_incomplete(current_container: Any | None, containers: list[Any]) -> bool:
    if current_container is None:
        return False

    labels = current_container.labels or {}
    depends_on = (labels.get("com.docker.compose.depends_on") or "").strip()
    if not depends_on:
        return False

    if len(containers) > 1:
        return False

    if len(containers) == 1 and containers[0].id != current_container.id:
        return False

    return True



def _shutdown_enable_guidance() -> str:
    return (
        "Restart with launcher defaults (`python run_server.py`) or explicitly enable socket override: "
        "`python run_server.py --compose-mode dev --with-docker-socket` "
        "or `docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.docker-socket.yml up -d --build`."
    )



def _docker_control_status() -> dict[str, Any]:
    if not _is_in_docker():
        return {
            "supported": False,
            "reason": "not_in_docker",
            "requires_socket_override": False,
            "detail": "Stack shutdown is available only when the API runs inside Docker.",
        }

    if not DOCKER_SOCKET_PATH.exists():
        return {
            "supported": False,
            "reason": "docker_socket_not_mounted",
            "requires_socket_override": True,
            "detail": "Docker socket is not mounted inside the API container.",
        }

    try:
        import docker
    except Exception as exc:
        logger.debug("admin_shutdown_docker_sdk_unavailable: %s", exc)
        return {
            "supported": False,
            "reason": "docker_sdk_unavailable",
            "requires_socket_override": False,
            "detail": "Docker SDK is not available in the API container.",
        }

    client = None
    try:
        client = docker.from_env()
        client.ping()
        current_container, containers, _ = _discover_shutdown_targets(client)
        if not containers:
            return {
                "supported": False,
                "reason": "shutdown_targets_not_found",
                "requires_socket_override": False,
                "detail": "Compose stack containers could not be discovered from the API container.",
            }
        if _is_stack_target_incomplete(current_container, containers):
            return {
                "supported": False,
                "reason": "shutdown_targets_incomplete",
                "requires_socket_override": False,
                "detail": "Only the API container is discoverable; full stack shutdown cannot be guaranteed.",
            }
        return {
            "supported": True,
            "reason": "ok",
            "requires_socket_override": False,
            "detail": "Docker control is available.",
        }
    except Exception as exc:
        logger.debug("admin_shutdown_docker_control_unavailable: %s", exc)
        return {
            "supported": False,
            "reason": "docker_control_unavailable",
            "requires_socket_override": True,
            "detail": "Cannot access Docker daemon from the API container.",
        }
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                logger.debug("admin_shutdown_client_close_failed: %s", exc)



def _shutdown_unavailable_payload(status_info: dict[str, Any]) -> dict[str, Any]:
    detail = status_info.get("detail") or "Stack shutdown is unavailable."
    if status_info.get("requires_socket_override"):
        detail = f"{detail} {_shutdown_enable_guidance()}"

    return {
        "code": status_info.get("reason") or "shutdown_unavailable",
        "message": status_info.get("detail") or "Stack shutdown is unavailable.",
        "detail": detail,
        "requires_socket_override": bool(status_info.get("requires_socket_override")),
    }


def _empty_content_summary() -> dict[str, Any]:
    return {
        "totals": 0,
        "statusCounts": {"pending": 0, "approved": 0, "hidden": 0},
        "topPromptVersions": [],
        "recentPendingProblems": [],
    }


def _empty_ops_summary(window_hours: int = 24) -> dict[str, Any]:
    return {
        "windowHours": window_hours,
        "total": 0,
        "statusCounts": {"success": 0, "failure": 0, "review_required": 0},
        "topEventTypes": [],
        "modeSummary": [],
        "latest": [],
    }


def _collect_admin_platform_summaries(*, window_hours: int = 24) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from sqlalchemy import case, func

        from app.db.models import PlatformOpsEvent, Problem, ProblemContentStatus
        from app.db.session import SessionLocal
        from app.db.base import utcnow
    except Exception as exc:
        logger.debug("admin_metrics_platform_import_failed: %s", exc)
        return _empty_content_summary(), _empty_ops_summary(window_hours)

    content_summary = _empty_content_summary()
    ops_summary = _empty_ops_summary(window_hours)
    window_start = utcnow() - timedelta(hours=window_hours)

    try:
        with SessionLocal() as db:
            content_summary["totals"] = int(db.query(func.count(Problem.id)).scalar() or 0)

            status_rows = (
                db.query(Problem.content_status, func.count(Problem.id))
                .group_by(Problem.content_status)
                .all()
            )
            for status_name, count in status_rows:
                key = getattr(status_name, "value", str(status_name or "")).strip().lower()
                if key:
                    content_summary["statusCounts"][key] = int(count or 0)

            prompt_rows = (
                db.query(Problem.prompt_version, func.count(Problem.id))
                .filter(Problem.prompt_version.isnot(None), Problem.prompt_version != "")
                .group_by(Problem.prompt_version)
                .order_by(func.count(Problem.id).desc(), Problem.prompt_version.asc())
                .limit(5)
                .all()
            )
            content_summary["topPromptVersions"] = [
                {"version": str(version), "count": int(count or 0)}
                for version, count in prompt_rows
                if str(version or "").strip()
            ]

            pending_rows = (
                db.query(Problem)
                .filter(Problem.content_status == ProblemContentStatus.pending)
                .order_by(Problem.created_at.desc(), Problem.id.desc())
                .limit(5)
                .all()
            )
            content_summary["recentPendingProblems"] = [
                {
                    "id": int(problem.id),
                    "title": str(problem.title or "제목 없는 문제"),
                    "mode": getattr(problem.kind, "value", str(problem.kind or "")),
                    "promptVersion": str(problem.prompt_version or ""),
                    "createdAt": problem.created_at.isoformat() if problem.created_at else None,
                }
                for problem in pending_rows
            ]

            ops_summary["total"] = int(
                db.query(func.count(PlatformOpsEvent.id))
                .filter(PlatformOpsEvent.created_at >= window_start)
                .scalar()
                or 0
            )

            status_counts = (
                db.query(PlatformOpsEvent.status, func.count(PlatformOpsEvent.id))
                .filter(PlatformOpsEvent.created_at >= window_start)
                .group_by(PlatformOpsEvent.status)
                .all()
            )
            for status_name, count in status_counts:
                key = str(status_name or "").strip().lower()
                if key:
                    ops_summary["statusCounts"][key] = int(count or 0)

            event_type_rows = (
                db.query(PlatformOpsEvent.event_type, func.count(PlatformOpsEvent.id))
                .filter(PlatformOpsEvent.created_at >= window_start)
                .group_by(PlatformOpsEvent.event_type)
                .order_by(func.count(PlatformOpsEvent.id).desc(), PlatformOpsEvent.event_type.asc())
                .limit(6)
                .all()
            )
            ops_summary["topEventTypes"] = [
                {"eventType": str(event_type), "count": int(count or 0)}
                for event_type, count in event_type_rows
            ]

            mode_rows = (
                db.query(
                    PlatformOpsEvent.mode,
                    func.count(PlatformOpsEvent.id),
                    func.sum(case((PlatformOpsEvent.status == "failure", 1), else_=0)),
                    func.avg(PlatformOpsEvent.latency_ms),
                )
                .filter(
                    PlatformOpsEvent.created_at >= window_start,
                    PlatformOpsEvent.mode.isnot(None),
                )
                .group_by(PlatformOpsEvent.mode)
                .order_by(func.count(PlatformOpsEvent.id).desc(), PlatformOpsEvent.mode.asc())
                .all()
            )
            ops_summary["modeSummary"] = [
                {
                    "mode": str(mode),
                    "total": int(total or 0),
                    "failure": int(failure or 0),
                    "avgLatencyMs": round(float(avg_latency or 0.0), 2),
                }
                for mode, total, failure, avg_latency in mode_rows
                if str(mode or "").strip()
            ]

            latest_rows = (
                db.query(PlatformOpsEvent)
                .filter(PlatformOpsEvent.created_at >= window_start)
                .order_by(PlatformOpsEvent.created_at.desc(), PlatformOpsEvent.id.desc())
                .limit(10)
                .all()
            )
            ops_summary["latest"] = [
                {
                    "id": int(event.id),
                    "eventType": str(event.event_type or ""),
                    "mode": str(event.mode or ""),
                    "status": str(event.status or ""),
                    "latencyMs": int(event.latency_ms or 0) if event.latency_ms is not None else None,
                    "requestId": str(event.request_id or ""),
                    "createdAt": event.created_at.isoformat() if event.created_at else None,
                }
                for event in latest_rows
            ]
    except Exception as exc:
        logger.debug("admin_metrics_platform_summary_failed: %s", exc)
        return _empty_content_summary(), _empty_ops_summary(window_hours)

    return content_summary, ops_summary


class _AdminKeyGuard:
    def __init__(
        self,
        settings: Any,
        *,
        max_failed_attempts: int = 5,
        failed_window_seconds: int = 60,
        block_seconds: int = 120,
    ):
        self.settings = settings
        self.max_failed_attempts = max_failed_attempts
        self.failed_window_seconds = failed_window_seconds
        self.block_seconds = block_seconds

        self._lock = threading.Lock()
        self._failed_attempts: dict[str, list[float]] = {}
        self._blocked_until: dict[str, float] = {}

    def _prune_state(self, now: float) -> None:
        for key, until in list(self._blocked_until.items()):
            if until <= now:
                self._blocked_until.pop(key, None)

        for key, attempts in list(self._failed_attempts.items()):
            kept = [ts for ts in attempts if (now - ts) <= self.failed_window_seconds]
            if kept:
                self._failed_attempts[key] = kept
            else:
                self._failed_attempts.pop(key, None)

    def require(
        self,
        request: Request,
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
        x_admin_key_b64: str | None = Header(default=None, alias="X-Admin-Key-B64"),
    ) -> None:
        expected = (self.settings.admin_panel_key or "").strip()
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin panel key is not configured.",
            )

        provided = self._extract_admin_key(x_admin_key=x_admin_key, x_admin_key_b64=x_admin_key_b64)
        client_id = request.client.host if request.client and request.client.host else "unknown"
        now = time.time()

        with self._lock:
            self._prune_state(now)

            is_valid = bool(provided) and hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))
            if is_valid:
                self._failed_attempts.pop(client_id, None)
                self._blocked_until.pop(client_id, None)
                return

            until = self._blocked_until.get(client_id)
            if until and until > now:
                retry_after = max(1, int(until - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many invalid admin key attempts. Try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

            attempts = self._failed_attempts.get(client_id, [])
            attempts.append(now)
            attempts = [ts for ts in attempts if (now - ts) <= self.failed_window_seconds]
            self._failed_attempts[client_id] = attempts

            if len(attempts) >= self.max_failed_attempts:
                self._failed_attempts.pop(client_id, None)
                self._blocked_until[client_id] = now + self.block_seconds
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many invalid admin key attempts. Try again later.",
                    headers={"Retry-After": str(self.block_seconds)},
                )

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key.")

    @staticmethod
    def _extract_admin_key(*, x_admin_key: str | None, x_admin_key_b64: str | None) -> str:
        raw = (x_admin_key or "").strip()
        if raw:
            return raw

        encoded = (x_admin_key_b64 or "").strip()
        if not encoded:
            return ""

        try:
            payload = encoded.encode("ascii")
            padding = b"=" * ((4 - len(payload) % 4) % 4)
            decoded = base64.urlsafe_b64decode(payload + padding)
            return decoded.decode("utf-8").strip()
        except Exception:
            return ""


class _ShutdownGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requested = False

    def request(self) -> bool:
        with self._lock:
            if self._requested:
                return False
            self._requested = True
            return True

    def release(self) -> None:
        with self._lock:
            self._requested = False



def _shutdown_local_process(delay_seconds: float = 1.0) -> None:
    time.sleep(delay_seconds)
    os._exit(0)



def _resolve_current_container(client: Any) -> Any | None:
    hints = _self_container_hints()

    for hint in hints:
        try:
            return client.containers.get(hint)
        except Exception as exc:
            logger.debug("admin_shutdown_resolve_hint_failed: hint=%s error=%s", hint, exc)
            continue

    try:
        for candidate in client.containers.list(all=True):
            for hint in hints:
                if candidate.id.startswith(hint) or candidate.name == hint:
                    return candidate
    except Exception as exc:
        logger.debug("admin_shutdown_list_all_failed: %s", exc)

    try:
        api_candidates = client.containers.list(all=True, filters={"label": "com.docker.compose.service=api"})
        if len(api_candidates) == 1:
            return api_candidates[0]
    except Exception as exc:
        logger.debug("admin_shutdown_list_api_candidates_failed: %s", exc)

    return None



def _resolve_project_name(current_container: Any | None) -> str:
    if current_container is not None:
        project_name = (current_container.labels or {}).get("com.docker.compose.project", "")
        if project_name:
            return project_name.strip()

    return (os.getenv("COMPOSE_PROJECT_NAME") or "").strip()



def _list_project_containers(client: Any, project_name: str, current_container: Any | None) -> list[Any]:
    if project_name:
        try:
            containers = client.containers.list(
                all=True,
                filters={"label": f"com.docker.compose.project={project_name}"},
            )
            if containers:
                return containers
        except Exception as exc:
            logger.debug(
                "admin_shutdown_list_project_containers_failed: project=%s error=%s",
                project_name,
                exc,
            )

    if current_container is not None:
        labels = current_container.labels or {}
        for label_key in (
            "com.docker.compose.project.working_dir",
            "com.docker.compose.project.config_files",
        ):
            label_value = (labels.get(label_key) or "").strip()
            if not label_value:
                continue
            try:
                containers = client.containers.list(
                    all=True,
                    filters={"label": f"{label_key}={label_value}"},
                )
            except Exception as exc:
                logger.debug(
                    "admin_shutdown_list_label_containers_failed: label=%s value=%s error=%s",
                    label_key,
                    label_value,
                    exc,
                )
                containers = []
            if containers:
                return containers

    if current_container is not None:
        return [current_container]
    return []



def _pick_api_container(containers: list[Any]) -> Any | None:
    for candidate in containers:
        if candidate.labels.get("com.docker.compose.service") == "api":
            return candidate
    return None



def _discover_shutdown_targets(client: Any) -> tuple[Any | None, list[Any], str]:
    current_container = _resolve_current_container(client)
    project_name = _resolve_project_name(current_container)
    containers = _list_project_containers(client, project_name, current_container)

    if current_container is None:
        current_container = _pick_api_container(containers)

    return current_container, containers, project_name



def _stop_and_remove_container(container: Any) -> None:
    try:
        container.reload()
        container.update(restart_policy={"Name": "no"})
        if container.status == "running":
            container.stop(timeout=20)
        container.remove(force=True)
    except Exception as exc:
        logger.exception("admin_shutdown_stop_remove_failed: container=%s error=%s", container.name, exc)



def _shutdown_compose_stack() -> bool:
    time.sleep(1.2)

    try:
        import docker
    except Exception as exc:
        logger.exception("admin_shutdown_docker_import_failed: %s", exc)
        return False

    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:
        logger.exception("admin_shutdown_docker_daemon_unavailable: %s", exc)
        return False

    current_container, containers, project_name = _discover_shutdown_targets(client)

    if _is_stack_target_incomplete(current_container, containers):
        logger.warning(
            "admin_shutdown_discovery_failed: project=%s reason=targets_incomplete",
            project_name or "unknown",
        )
        return False

    ordered = [c for c in containers if current_container is None or c.id != current_container.id]
    for container in ordered:
        _stop_and_remove_container(container)

    if current_container is None:
        if containers:
            return True
        logger.warning("admin_shutdown_no_target_containers_found")
        return False

    try:
        current_container.reload()
        current_container.update(restart_policy={"Name": "no"})
        current_container.remove(force=True)
        return True
    except Exception as exc:
        logger.exception("admin_shutdown_remove_current_container_failed: %s", exc)
        return False



def _shutdown_runtime_stack() -> bool:
    if _is_in_docker():
        return _shutdown_compose_stack()

    _shutdown_local_process()
    return True



def register_admin_api(
    *,
    app: FastAPI,
    settings: Any,
    admin_metrics: Any,
    admin_file: Path,
) -> None:
    shutdown_gate = _ShutdownGate()
    admin_guard = _AdminKeyGuard(settings)

    def _run_shutdown_task() -> None:
        try:
            completed = _shutdown_runtime_stack()
        except Exception:
            shutdown_gate.release()
            raise
        if not completed:
            shutdown_gate.release()

    @app.get("/admin.html", include_in_schema=False)
    def admin_page() -> Response:
        frontend_dir = admin_file.parent
        responsive_admin = frontend_dir / "app" / "admin.html"
        if not responsive_admin.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin page not found")

        return render_template_response(
            responsive_admin,
            frontend_dir=frontend_dir,
            template_variant="responsive",
            vary_user_agent=False,
        )

    @app.get("/api/admin/metrics")
    def admin_metrics_snapshot(_: None = Depends(admin_guard.require)) -> dict:
        snapshot = admin_metrics.snapshot()
        status_info = _docker_control_status()
        content_summary, ops_events = _collect_admin_platform_summaries(window_hours=24)
        snapshot["admin"] = {
            "shutdown": {
                "supported": bool(status_info.get("supported")),
                "reason": status_info.get("reason") or "unknown",
                "requires_socket_override": bool(status_info.get("requires_socket_override")),
            },
            "contentSummary": content_summary,
            "opsEvents": ops_events,
        }
        if not status_info.get("supported"):
            snapshot["admin"]["shutdown"]["detail"] = _shutdown_unavailable_payload(status_info)["detail"]
        return snapshot

    @app.post("/api/admin/shutdown")
    def admin_shutdown(
        background_tasks: BackgroundTasks,
        _: None = Depends(admin_guard.require),
    ) -> dict:
        status_info = _docker_control_status()
        if not status_info.get("supported"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_shutdown_unavailable_payload(status_info),
            )

        if not shutdown_gate.request():
            return {"status": "already_requested", "detail": "Shutdown already in progress."}

        background_tasks.add_task(_run_shutdown_task)
        return {"status": "accepted", "detail": "Shutdown has been scheduled."}





