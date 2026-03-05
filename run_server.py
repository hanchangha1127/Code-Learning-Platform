"""Entrypoint module for the code learning platform."""

from __future__ import annotations

from server_runtime.webapp import app


if __name__ == "__main__":
    from server_runtime.launcher import main

    raise SystemExit(main())
