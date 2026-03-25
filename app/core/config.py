from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


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


def _resolve_secret_value(value: str | None, file_path: str | None) -> str | None:
    direct = _normalize_optional(value)
    if direct:
        return direct
    return _read_secret_file(file_path)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    APP_ENV: str = "development"

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "code_platform"
    DB_USER: str = "appuser"
    DB_PASSWORD: str = ""
    DB_PASSWORD_FILE: str | None = None

    JWT_SECRET: str = ""
    JWT_SECRET_FILE: str | None = None
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRES_MIN: int = 30
    REFRESH_TOKEN_EXPIRES_DAYS: int = 14
    ALLOW_PLATFORM_PASSWORD_AUTH: bool = False

    AI_PROVIDER: str = "mock"
    AI_API_KEY: str | None = None
    AI_API_KEY_FILE: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_API_KEY_FILE: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_REQUEST_TIMEOUT_SECONDS: int = 30

    ANALYSIS_QUEUE_MODE: str = "inline"
    ANALYSIS_QUEUE_NAME: str = "analysis"
    PROBLEM_FOLLOW_UP_QUEUE_MODE: str = "inline"
    PROBLEM_FOLLOW_UP_QUEUE_NAME: str = "problem-follow-up"
    ANALYSIS_QUEUE_JOB_TIMEOUT_SECONDS: int = 300
    ANALYSIS_QUEUE_RESULT_TTL_SECONDS: int = 3600
    ANALYSIS_QUEUE_FAILURE_TTL_SECONDS: int = 86400
    ANALYSIS_PROCESSING_STALE_SECONDS: int = 900

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_PASSWORD_FILE: str | None = None
    ADMIN_THROTTLE_BACKEND: str = "redis"
    ALLOW_SIDLESS_COOKIE_COMPAT: bool = Field(
        default=False,
        validation_alias="CODE_PLATFORM_ALLOW_SIDLESS_COOKIE_COMPAT",
    )
    SIDLESS_COOKIE_SUNSET_AT: str = Field(
        default="2026-04-03T23:59:59+09:00",
        validation_alias="CODE_PLATFORM_SIDLESS_COOKIE_SUNSET_AT",
    )

    @model_validator(mode="after")
    def _resolve_and_validate_security_settings(self) -> "Settings":
        self.DB_PASSWORD = _resolve_secret_value(self.DB_PASSWORD, self.DB_PASSWORD_FILE) or ""
        self.JWT_SECRET = _resolve_secret_value(self.JWT_SECRET, self.JWT_SECRET_FILE) or ""
        self.AI_API_KEY = _resolve_secret_value(self.AI_API_KEY, self.AI_API_KEY_FILE)
        self.OPENAI_API_KEY = _resolve_secret_value(self.OPENAI_API_KEY, self.OPENAI_API_KEY_FILE)
        self.REDIS_PASSWORD = _resolve_secret_value(self.REDIS_PASSWORD, self.REDIS_PASSWORD_FILE)
        self.ADMIN_THROTTLE_BACKEND = (self.ADMIN_THROTTLE_BACKEND or "redis").strip().lower() or "redis"
        self.ANALYSIS_QUEUE_MODE = (self.ANALYSIS_QUEUE_MODE or "inline").strip().lower() or "inline"
        self.PROBLEM_FOLLOW_UP_QUEUE_MODE = (
            (self.PROBLEM_FOLLOW_UP_QUEUE_MODE or "inline").strip().lower() or "inline"
        )

        if not self.DB_PASSWORD.strip():
            raise ValueError("DB_PASSWORD must be set via environment variable or DB_PASSWORD_FILE.")

        secret = self.JWT_SECRET.strip()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters.")

        env_name = (self.APP_ENV or "").strip().lower()
        if env_name not in {"dev", "development", "local", "test"} and secret.startswith("dev-"):
            raise ValueError("JWT_SECRET uses a development prefix in a non-development environment.")
        if self.ADMIN_THROTTLE_BACKEND not in {"redis", "memory"}:
            raise ValueError("ADMIN_THROTTLE_BACKEND must be either 'redis' or 'memory'.")
        if self.ANALYSIS_QUEUE_MODE not in {"inline", "rq"}:
            raise ValueError("ANALYSIS_QUEUE_MODE must be either 'inline' or 'rq'.")
        if self.PROBLEM_FOLLOW_UP_QUEUE_MODE not in {"inline", "rq"}:
            raise ValueError("PROBLEM_FOLLOW_UP_QUEUE_MODE must be either 'inline' or 'rq'.")

        return self

    @property
    def DATABASE_URL(self) -> str:
        return URL.create(
            "mysql+pymysql",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        ).render_as_string(hide_password=False)

    @property
    def RESOLVED_AI_API_KEY(self) -> str | None:
        key = self.AI_API_KEY or self.OPENAI_API_KEY
        normalized = _normalize_optional(key)
        return normalized or None


settings = Settings()
