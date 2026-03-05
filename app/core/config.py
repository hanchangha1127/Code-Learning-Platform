from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    APP_ENV: str = "development"

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "code_platform"
    DB_USER: str = "appuser"
    DB_PASSWORD: str = ""

    JWT_SECRET: str = ""
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRES_MIN: int = 30
    REFRESH_TOKEN_EXPIRES_DAYS: int = 14

    AI_PROVIDER: str = "mock"
    AI_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_REQUEST_TIMEOUT_SECONDS: int = 30

    ANALYSIS_QUEUE_MODE: str = "inline"  # rq | inline
    ANALYSIS_QUEUE_NAME: str = "analysis"
    ANALYSIS_QUEUE_JOB_TIMEOUT_SECONDS: int = 300
    ANALYSIS_QUEUE_RESULT_TTL_SECONDS: int = 3600
    ANALYSIS_QUEUE_FAILURE_TTL_SECONDS: int = 86400
    ANALYSIS_PROCESSING_STALE_SECONDS: int = 900

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    @model_validator(mode="after")
    def _validate_security_settings(self) -> "Settings":
        if not self.DB_PASSWORD.strip():
            raise ValueError("DB_PASSWORD must be set via environment variable.")

        secret = self.JWT_SECRET.strip()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters.")

        env_name = (self.APP_ENV or "").strip().lower()
        if env_name not in {"dev", "development", "local", "test"} and secret.startswith("dev-"):
            raise ValueError("JWT_SECRET uses a development prefix in a non-development environment.")

        return self

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def RESOLVED_AI_API_KEY(self) -> str | None:
        key = self.AI_API_KEY or self.OPENAI_API_KEY
        if not key:
            return None
        normalized = key.strip()
        return normalized or None


settings = Settings()
