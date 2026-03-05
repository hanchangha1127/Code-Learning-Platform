from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict:
    return {"status": "ok", "platform_backend": "/platform"}
