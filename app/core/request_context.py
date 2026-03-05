from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str | None) -> None:
    token = str(request_id or "").strip()
    _request_id_var.set(token or None)


def get_request_id() -> str | None:
    return _request_id_var.get()


def ensure_request_id() -> str:
    current = get_request_id()
    if current:
        return current
    generated = uuid4().hex
    set_request_id(generated)
    return generated
