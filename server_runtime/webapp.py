"""FastAPI server assembly for the code learning platform prototype."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.main import app as platform_backend_app
from app.core.request_context import ensure_request_id, set_request_id
from server_runtime.admin_api import register_admin_api
from server_runtime.context import ADMIN_FILE, FRONTEND_DIR, admin_metrics, request_client_id, settings
from server_runtime.routes import auth_router, health_router, learning_router, pages_router

logger = logging.getLogger(__name__)

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
    "/api/code-calc/problem": "/platform/codecalc/problem",
    "/api/code-calc/submit": "/platform/codecalc/submit",
    "/api/code-error/problem": "/platform/codeerror/problem",
    "/api/code-error/submit": "/platform/codeerror/submit",
    "/api/auditor/problem": "/platform/auditor/problem",
    "/api/auditor/submit": "/platform/auditor/submit",
    "/api/context-inference/problem": "/platform/context-inference/problem",
    "/api/context-inference/submit": "/platform/context-inference/submit",
    "/api/refactoring-choice/problem": "/platform/refactoring-choice/problem",
    "/api/refactoring-choice/submit": "/platform/refactoring-choice/submit",
    "/api/code-blame/problem": "/platform/code-blame/problem",
    "/api/code-blame/submit": "/platform/code-blame/submit",
}


def _resolve_moved_api_path(path: str) -> str | None:
    if path.startswith("/api/auth/"):
        return "/platform/auth/" + path.removeprefix("/api/auth/")
    return _MOVED_API_PATHS.get(path)

app = FastAPI(title="code-learning-platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.allow_legacy_jsonl_tokens:
    logger.warning(
        "Legacy JSONL token compatibility is enabled. "
        "Set CODE_PLATFORM_ALLOW_LEGACY_JSONL_TOKENS=false before %s.",
        settings.legacy_token_sunset_date,
    )


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


@app.middleware("http")
async def redirect_moved_api_paths(request: Request, call_next):
    new_path = _resolve_moved_api_path(request.url.path)
    if new_path is None:
        return await call_next(request)

    return JSONResponse(
        status_code=410,
        content={
            "detail": "이 경로는 더 이상 지원되지 않습니다. /platform 경로를 사용해 주세요.",
            "code": "moved_to_platform",
            "oldPath": request.url.path,
            "newPath": new_path,
        },
        headers={"Cache-Control": "no-store"},
    )


if FRONTEND_DIR.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

app.mount("/platform", platform_backend_app)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(learning_router)
app.include_router(pages_router)

register_admin_api(
    app=app,
    settings=settings,
    admin_metrics=admin_metrics,
    admin_file=ADMIN_FILE,
)
