"""Configuration helpers for the backend service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _get_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or default


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _read_secret_file(path_value: str | None) -> str | None:
    path_text = _normalize_optional(path_value)
    if not path_text:
        return None
    secret_path = Path(path_text)
    if not secret_path.exists() or not secret_path.is_file():
        return None
    try:
        raw = secret_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _normalize_optional(raw)


def _get_secret_env(*names: str) -> str | None:
    """Resolve secret-like values from env vars or *_FILE indirection."""

    for name in names:
        direct = _normalize_optional(os.getenv(name))
        if direct:
            return direct

        from_file = _read_secret_file(os.getenv(f"{name}_FILE"))
        if from_file:
            return from_file

    return None


def _load_env_file() -> None:
    """Load key=value pairs from optional env files if they exist.

    Only sets variables that are not already defined in the current environment.
    """

    root = Path(__file__).resolve().parent.parent
    for candidate in (".env", "env.txt"):
        env_path = root / candidate
        if not env_path.exists():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    continue
                if key in os.environ:
                    continue
                normalized = value.strip().strip('"').strip("'")
                # Skip empty values so a blank entry in .env doesn't override real environment variables.
                if not normalized:
                    continue
                os.environ[key] = normalized
        except OSError:
            # Ignore read errors and try the next file.
            continue


_load_env_file()


@dataclass(frozen=True)
class Settings:
    """Application-wide configuration resolved from environment variables."""

    data_dir: Path = Path(os.getenv("CODE_PLATFORM_DATA_DIR", "data")).resolve()
    users_dir: Path = Path(os.getenv("CODE_PLATFORM_USERS_DIR", "data/users")).resolve()
    ai_api_key: Optional[str] = _get_secret_env("AI_API_KEY")
    google_api_key: Optional[str] = _get_secret_env("GOOGLE_API_KEY")
    google_model: str = os.getenv("GOOGLE_MODEL", "gemini-3-flash-preview")
    google_oauth_client_id: Optional[str] = _get_secret_env("GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: Optional[str] = _get_secret_env("GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: Optional[str] = _normalize_optional(os.getenv("GOOGLE_OAUTH_REDIRECT_URI"))
    google_api_endpoint: str = os.getenv(
        "GOOGLE_API_ENDPOINT", "https://generativelanguage.googleapis.com"
    )
    guest_ttl_seconds: int = _get_int_env("CODE_PLATFORM_GUEST_TTL_SECONDS", 300)
    admin_panel_key: str = os.getenv("ADMIN_PANEL_KEY", "")
    admin_metrics_window_minutes: int = _get_int_env("ADMIN_METRICS_WINDOW_MINUTES", 60)
    admin_active_window_seconds: int = _get_int_env("ADMIN_ACTIVE_WINDOW_SECONDS", 300)
    allow_legacy_jsonl_tokens: bool = _get_bool_env("CODE_PLATFORM_ALLOW_LEGACY_JSONL_TOKENS", False)
    legacy_token_sunset_date: str = os.getenv("CODE_PLATFORM_LEGACY_TOKEN_SUNSET_DATE", "2026-03-31")
    cors_origins: tuple[str, ...] = _get_csv_env(
        "CODE_PLATFORM_CORS_ORIGINS",
        ("http://127.0.0.1:8000", "http://localhost:8000"),
    )


def get_settings() -> Settings:
    """Return singleton-style settings."""

    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.users_dir.mkdir(parents=True, exist_ok=True)
    return settings
