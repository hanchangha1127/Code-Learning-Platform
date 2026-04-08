"""Entrypoint module for the code learning platform."""

from __future__ import annotations

from server.app import app


if __name__ == "__main__":
    from server.launcher import main

    raise SystemExit(main())

