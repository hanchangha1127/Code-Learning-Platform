"""FastAPI app assembly for the code learning platform."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.bootstrap import ADMIN_FILE, FRONTEND_DIR, admin_metrics, request_client_id, settings
from server.core.request_context import ensure_request_id, set_request_id
from server.features.account.api import router as account_router
from server.features.auth.api import router as platform_auth_router
from server.features.auth.legacy_api import router as auth_router
from server.features.jobs.api import router as platform_mode_jobs_router
from server.features.learning.api import router as learning_router
from server.features.learning.legacy_api import router as learning_legacy_router
from server.features.reports.api import router as reports_router
from server.features.runtime_ui.admin import register_admin_api
from server.features.runtime_ui.health import router as health_router
from server.features.runtime_ui.pages import router as pages_router

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_RUNTIME_ROUTERS = (
    health_router,
    auth_router,
    learning_legacy_router,
    pages_router,
)
_MOVED_API_PATHS = {
    "/api/languages": "/platform/languages",
    "/api/profile": "/platform/profile",
    "/api/me": "/platform/me",
    "/api/report": "/platform/report",
    "/api/learning/history": "/platform/learning/history",
    "/api/learning/memory": "/platform/learning/memory",
    "/api/diagnostics/start": "/platform/analysis/problem",
    "/api/problem/submit": "/platform/analysis/submit",
    "/api/code-block/problem": "/platform/codeblock/problem",
    "/api/code-block/submit": "/platform/codeblock/submit",
    "/api/code-arrange/problem": "/platform/arrange/problem",
    "/api/code-arrange/submit": "/platform/arrange/submit",
    "/api/auditor/problem": "/platform/auditor/problem",
    "/api/auditor/submit": "/platform/auditor/submit",
    "/api/refactoring-choice/problem": "/platform/refactoring-choice/problem",
    "/api/refactoring-choice/submit": "/platform/refactoring-choice/submit",
    "/api/code-blame/problem": "/platform/code-blame/problem",
    "/api/code-blame/submit": "/platform/code-blame/submit",
}
_MOVED_AUTH_PATHS = {
    "/api/auth/register": "/platform/auth/signup",
    "/api/auth/login": "/platform/auth/login",
    "/api/auth/logout": "/platform/auth/logout",
    "/api/auth/guest": "/platform/auth/guest",
    "/api/auth/guest/start": "/platform/auth/guest",
    "/api/auth/google/start": "/platform/auth/google/start",
    "/api/auth/google/callback": "/platform/auth/google/callback",
}

_platform_health_router = APIRouter()


@_platform_health_router.get("/health")
def platform_health() -> dict[str, str]:
    return {"status": "ok"}


def _resolve_moved_api_path(path: str) -> str | None:
    explicit_auth_path = _MOVED_AUTH_PATHS.get(path)
    if explicit_auth_path is not None:
        return explicit_auth_path
    if path.startswith("/api/auth/"):
        return "/platform/auth/" + path.removeprefix("/api/auth/")
    return _MOVED_API_PATHS.get(path)


def _is_loopback_origin(origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return (parsed.hostname or "").lower() in _LOOPBACK_HOSTS


def _credentialed_cors_origins(origins: tuple[str, ...]) -> list[str]:
    sanitized: list[str] = []
    seen: set[str] = set()
    for raw_origin in origins:
        origin = str(raw_origin or "").strip().rstrip("/")
        if not origin:
            continue
        try:
            parsed = urlsplit(origin)
        except ValueError:
            logger.warning("Dropping invalid CORS origin: %s", raw_origin)
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.warning("Dropping invalid CORS origin: %s", raw_origin)
            continue
        if parsed.scheme == "http" and not _is_loopback_origin(origin):
            logger.warning("Dropping insecure credentialed CORS origin: %s", raw_origin)
            continue
        if origin in seen:
            continue
        seen.add(origin)
        sanitized.append(origin)
    return sanitized


def _moved_api_response(path: str, new_path: str) -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={
            "detail": "이 경로는 더 이상 지원되지 않습니다. /platform 경로를 사용해 주세요.",
            "code": "moved_to_platform",
            "oldPath": path,
            "newPath": new_path,
        },
        headers={"Cache-Control": "no-store"},
    )


def _configure_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_credentialed_cors_origins(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _warn_legacy_jsonl_compatibility() -> None:
    if settings.allow_legacy_jsonl_tokens:
        logger.warning(
            "Legacy JSONL token compatibility is enabled. "
            "Set CODE_PLATFORM_ALLOW_LEGACY_JSONL_TOKENS=false before %s.",
            settings.legacy_token_sunset_date,
        )


def _register_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        set_request_id(request.headers.get("x-request-id"))
        request_id = ensure_request_id()
        try:
            response = await call_next(request)
        finally:
            set_request_id(None)
        response.headers["X-Request-Id"] = request_id
        return response


def _register_runtime_metrics_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def record_runtime_metrics(request: Request, call_next):
        client_id = request_client_id(request)
        admin_metrics.record_request_start(path=request.url.path, client_id=client_id)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            admin_metrics.record_request_end(status_code=status_code)


def _register_legacy_redirect_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def redirect_moved_api_paths(request: Request, call_next):
        new_path = _resolve_moved_api_path(request.url.path)
        if new_path is None:
            return await call_next(request)
        return _moved_api_response(request.url.path, new_path)


def _register_runtime_middleware(app: FastAPI) -> None:
    _register_request_id_middleware(app)
    _register_runtime_metrics_middleware(app)
    _register_legacy_redirect_middleware(app)


def _mount_runtime_static(app: FastAPI) -> None:
    if FRONTEND_DIR.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def _include_runtime_routes(app: FastAPI) -> None:
    for router in _RUNTIME_ROUTERS:
        app.include_router(router)


def _join_route_prefix(prefix: str, suffix: str) -> str:
    base = prefix.rstrip("/")
    if not base:
        return suffix
    return f"{base}{suffix}"


def _include_platform_routes(app: FastAPI, *, prefix: str = "") -> None:
    app.include_router(_platform_health_router, prefix=prefix)
    app.include_router(platform_auth_router, prefix=_join_route_prefix(prefix, "/auth"), tags=["auth"])
    app.include_router(account_router, prefix=_join_route_prefix(prefix, "/me"), tags=["me"])
    app.include_router(learning_router, prefix=prefix, tags=["learning"])
    app.include_router(reports_router, prefix=prefix, tags=["reports"])
    app.include_router(
        platform_mode_jobs_router,
        prefix=_join_route_prefix(prefix, "/mode-jobs"),
        tags=["mode-jobs"],
    )


def _register_runtime_admin_api(app: FastAPI) -> None:
    register_admin_api(
        app=app,
        settings=settings,
        admin_metrics=admin_metrics,
        admin_file=ADMIN_FILE,
    )


def create_platform_app() -> FastAPI:
    app = FastAPI(title="code-platform")
    _register_request_id_middleware(app)
    _include_platform_routes(app)
    return app


def create_app() -> FastAPI:
    app = FastAPI(title="code-learning-platform", version="0.1.0")
    _configure_cors(app)
    _warn_legacy_jsonl_compatibility()
    _register_runtime_middleware(app)
    _mount_runtime_static(app)
    _include_platform_routes(app, prefix="/platform")
    _include_runtime_routes(app)
    _register_runtime_admin_api(app)
    return app


platform_app = create_platform_app()
app = create_app()
_shared_dependency_overrides: dict = {}
platform_app.dependency_overrides = _shared_dependency_overrides
app.dependency_overrides = _shared_dependency_overrides
