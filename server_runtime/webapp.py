"""FastAPI server assembly for the code learning platform prototype."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.main import app as platform_backend_app
from server_runtime.admin_api import register_admin_api
from server_runtime.context import ADMIN_FILE, FRONTEND_DIR, admin_metrics, request_client_id, settings
from server_runtime.routes import auth_router, health_router, learning_router, pages_router

logger = logging.getLogger(__name__)

app = FastAPI(title="code-learning-platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
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
