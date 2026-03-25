from __future__ import annotations

from fastapi import Response

from server_runtime.context import (
    learning_service as runtime_learning_service,
    set_access_cookie as runtime_set_access_cookie,
    storage_manager as runtime_storage_manager,
    user_service as runtime_user_service,
)

learning_service = runtime_learning_service
storage_manager = runtime_storage_manager
user_service = runtime_user_service


def set_platform_access_cookie(
    response: Response,
    token: str,
    *,
    sid: int | None = None,
    persistent: bool = False,
    refresh_token: str | None = None,
) -> None:
    _ = sid, persistent, refresh_token
    runtime_set_access_cookie(response, token)
