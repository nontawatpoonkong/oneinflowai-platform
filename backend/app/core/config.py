"""Application configuration.

All settings are loaded from environment variables (or a local `.env` file)
using pydantic-settings v2. Access the singleton via `get_settings()`.
"""

from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --------------------------------------------------------------- Email
    EMAIL_PROVIDER: str = "development"
    RESEND_API_KEY: str | None = None
    EMAIL_FROM_ADDRESS: str = "no-reply@oneflow.ai"
    EMAIL_FROM_NAME: str = "OneInFlow"
    EMAIL_VERIFICATION_OTP_TTL_SECONDS: int = 300
    EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS: int = 60
    EMAIL_VERIFICATION_MAX_ATTEMPTS: int = 5
    PASSWORD_RESET_TOKEN_TTL_SECONDS: int = 600
    OTP_HASH_SECRET: str | None = None

    # ------------------------------------------------------------- Storage
    STORAGE_PROVIDER: str = "local"
    STORAGE_LOCAL_PATH: str = "storage"
    KNOWLEDGE_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024
    KNOWLEDGE_MAX_EXTRACTED_CHARACTERS: int = 2_000_000

    # ------------------------------------------------------------------ App
    APP_NAME: str = "OneInFlow Platform"
    APP_ENV: str = "development"  # development | staging | production
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------- Logging
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # ------------------------------------------------------------ Postgres
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "oneflowai"
    POSTGRES_PASSWORD: str = "oneflowai"
    POSTGRES_DB: str = "oneflowai"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --------------------------------------------------------------- Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # -------------------------------------------------------------- Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str | None = None

    # ----------------------------------------------------------------- JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # -------------------------------------------------------------- Tenancy
    # Root domain used to resolve workspace subdomains (acme.oneflow.ai).
    BASE_DOMAIN: str = "oneflow.ai"

    # ------------------------------------------------------------ WebChat
    WEBCHAT_SESSION_TTL_DAYS: int = 90
    WEBCHAT_METADATA_HASH_SECRET: str = "change-me-webchat-metadata-secret"
    WEBCHAT_CUSTOMER_MERGE_ENABLED: bool = False

    # -------------------------------------------------- Derived / computed
    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL(self) -> str:
        """Async SQLAlchemy DSN (asyncpg driver)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URL(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def QDRANT_URL(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
