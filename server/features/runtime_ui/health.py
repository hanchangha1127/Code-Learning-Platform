from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
def healthcheck() -> dict:
    return {"status": "ok", "platform_backend": "/platform"}
