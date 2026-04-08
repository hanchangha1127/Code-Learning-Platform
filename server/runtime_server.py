from __future__ import annotations

import argparse
import threading
from collections.abc import Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
import uvicorn

from server.core.runtime_config import get_settings

HTTP_REDIRECT_STATUS = 307
HTTP_REDIRECT_METHODS: tuple[str, ...] = (
    "DELETE",
    "GET",
    "HEAD",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
)
DEFAULT_HTTP_PORT = 8000


def _normalize_host(host_header: str) -> tuple[str, int | None]:
    parsed = urlsplit(f"//{host_header}")
    hostname = parsed.hostname or host_header
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    return hostname, parsed.port


def build_https_redirect_target(request: Request, https_public_port: int) -> str:
    host_header = (request.headers.get("host") or request.url.netloc or "").strip()
    hostname, _port = _normalize_host(host_header)
    if https_public_port == 443:
        netloc = hostname
    else:
        netloc = f"{hostname}:{https_public_port}"

    query = request.url.query or ""
    path = request.url.path or "/"
    return urlunsplit(SplitResult("https", netloc, path, query, ""))


def create_http_redirect_app(*, https_public_port: int) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/", methods=list(HTTP_REDIRECT_METHODS), include_in_schema=False)
    @app.api_route("/{path:path}", methods=list(HTTP_REDIRECT_METHODS), include_in_schema=False)
    async def redirect_to_https(request: Request, path: str = ""):
        return RedirectResponse(
            url=build_https_redirect_target(request, https_public_port),
            status_code=HTTP_REDIRECT_STATUS,
        )

    return app


def resolve_runtime_bind_port(*, requested_port: int | None = None) -> int:
    settings = get_settings()
    if not settings.enable_https:
        return requested_port or DEFAULT_HTTP_PORT

    if requested_port is None or requested_port == DEFAULT_HTTP_PORT:
        return settings.https_bind_port
    return requested_port


class _RedirectServerThread(threading.Thread):
    def __init__(self, *, host: str, port: int, https_public_port: int) -> None:
        super().__init__(name="http-redirect-server", daemon=True)
        self._server = uvicorn.Server(
            uvicorn.Config(
                create_http_redirect_app(https_public_port=https_public_port),
                host=host,
                port=port,
                reload=False,
                workers=1,
                log_level="info",
            )
        )

    def run(self) -> None:
        self._server.run()

    def stop(self) -> None:
        self._server.should_exit = True


def _run_plain_http_server(*, host: str, port: int, workers: int) -> int:
    uvicorn.run("run_server:app", host=host, port=port, workers=workers, reload=False)
    return 0


def _run_https_server(*, host: str, port: int, workers: int) -> int:
    settings = get_settings()
    settings.validate_https_settings()

    redirect_server = _RedirectServerThread(
        host=host,
        port=settings.http_redirect_port,
        https_public_port=settings.https_public_port,
    )
    redirect_server.start()

    try:
        uvicorn.run(
            "run_server:app",
            host=host,
            port=port,
            workers=workers,
            reload=False,
            ssl_certfile=str(settings.resolved_ssl_certfile),
            ssl_keyfile=str(settings.resolved_ssl_keyfile),
        )
        return 0
    finally:
        redirect_server.stop()
        redirect_server.join(timeout=5)


def run_application_server(*, host: str, port: int | None = None, workers: int = 1) -> int:
    settings = get_settings()
    bind_port = resolve_runtime_bind_port(requested_port=port)
    if not settings.enable_https:
        return _run_plain_http_server(host=host, port=bind_port, workers=workers)
    return _run_https_server(host=host, port=bind_port, workers=workers)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the application server with optional direct HTTPS.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--workers", type=int, default=1)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run_application_server(host=args.host, port=args.port, workers=args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
