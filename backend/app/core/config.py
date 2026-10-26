"""Application configuration.

All settings are loaded from environment variables (or a local `.env` file)
using pydantic-settings v2. Access the singleton via `get_settings()`.
"""

from functools import lru_cache

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------- AI
    AI_PROVIDER: str = "openai"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-5.6-terra"
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-pro"
    GENERATION_PROVIDER: str = "openai"
    GENERATION_TEMPERATURE: float = 0.2
    GENERATION_MAX_OUTPUT_TOKENS: int = 800
    GENERATION_REQUEST_TIMEOUT_SECONDS: float = 45
    DEMO_CHAT_RATE_LIMIT_REQUESTS: int = 5
    DEMO_CHAT_RATE_LIMIT_WINDOW_SECONDS: int = 60
    DEMO_CHAT_MAX_INPUT_CHARS: int = 1000
    WEBCHAT_RATE_LIMIT_REQUESTS: int = 30
    WEBCHAT_RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_RATE_LIMIT_REQUESTS: int = 10
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60
    EMBEDDING_PROVIDER: str = "openai"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_BATCH_SIZE: int = 64
    EMBEDDING_REQUEST_TIMEOUT_SECONDS: float = 30

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
    KNOWLEDGE_CHUNK_SIZE: int = 1200
    KNOWLEDGE_CHUNK_OVERLAP: int = 200
    KNOWLEDGE_MAX_CHUNKS_PER_DOCUMENT: int = 10_000
    KNOWLEDGE_RETRIEVAL_DEFAULT_LIMIT: int = 5
    KNOWLEDGE_RETRIEVAL_MAX_LIMIT: int = 20
    KNOWLEDGE_RETRIEVAL_MAX_QUERY_CHARACTERS: int = 2000
    KNOWLEDGE_RETRIEVAL_SCORE_THRESHOLD: float | None = None
    RAG_MAX_CONTEXT_CHARACTERS: int = 12_000
    RAG_MAX_SOURCES: int = 8
    PAYMENT_EVIDENCE_MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024
    SLIP_VERIFICATION_PROVIDER: str = "development"
    EASYSLIP_API_KEY: str | None = None
    SLIP_VERIFICATION_TIMEOUT_SECONDS: float = 10.0
    ACTION_COLLECTION_PROVIDER: str = "development"
    ACTION_COLLECTION_SESSION_TTL_MINUTES: int = 30

    @model_validator(mode="after")
    def validate_knowledge_chunking(self) -> "Settings":
        if self.KNOWLEDGE_CHUNK_SIZE <= 0:
            raise ValueError("KNOWLEDGE_CHUNK_SIZE must be greater than zero")
        if self.KNOWLEDGE_CHUNK_OVERLAP < 0:
            raise ValueError("KNOWLEDGE_CHUNK_OVERLAP must be non-negative")
        if self.KNOWLEDGE_CHUNK_OVERLAP >= self.KNOWLEDGE_CHUNK_SIZE:
            raise ValueError(
                "KNOWLEDGE_CHUNK_OVERLAP must be less than KNOWLEDGE_CHUNK_SIZE"
            )
        if self.KNOWLEDGE_MAX_CHUNKS_PER_DOCUMENT <= 0:
            raise ValueError(
                "KNOWLEDGE_MAX_CHUNKS_PER_DOCUMENT must be greater than zero"
            )
        if not self.EMBEDDING_PROVIDER.strip():
            raise ValueError("EMBEDDING_PROVIDER must not be empty")
        if not self.OPENAI_EMBEDDING_MODEL.strip():
            raise ValueError("OPENAI_EMBEDDING_MODEL must not be empty")
        if self.EMBEDDING_BATCH_SIZE <= 0:
            raise ValueError("EMBEDDING_BATCH_SIZE must be greater than zero")
        if self.EMBEDDING_REQUEST_TIMEOUT_SECONDS <= 0:
            raise ValueError(
                "EMBEDDING_REQUEST_TIMEOUT_SECONDS must be greater than zero"
            )
        if not self.QDRANT_KNOWLEDGE_COLLECTION.strip():
            raise ValueError("QDRANT_KNOWLEDGE_COLLECTION must not be empty")
        if self.KNOWLEDGE_RETRIEVAL_DEFAULT_LIMIT <= 0:
            raise ValueError("KNOWLEDGE_RETRIEVAL_DEFAULT_LIMIT must be positive")
        if self.KNOWLEDGE_RETRIEVAL_MAX_LIMIT <= 0:
            raise ValueError("KNOWLEDGE_RETRIEVAL_MAX_LIMIT must be positive")
        if self.KNOWLEDGE_RETRIEVAL_DEFAULT_LIMIT > self.KNOWLEDGE_RETRIEVAL_MAX_LIMIT:
            raise ValueError("retrieval default limit must not exceed maximum")
        if self.KNOWLEDGE_RETRIEVAL_MAX_QUERY_CHARACTERS <= 0:
            raise ValueError("retrieval query maximum must be positive")
        if (
            self.KNOWLEDGE_RETRIEVAL_SCORE_THRESHOLD is not None
            and not -1 <= self.KNOWLEDGE_RETRIEVAL_SCORE_THRESHOLD <= 1
        ):
            raise ValueError("retrieval score threshold must be between -1 and 1")
        if self.RAG_MAX_CONTEXT_CHARACTERS <= 0:
            raise ValueError("RAG_MAX_CONTEXT_CHARACTERS must be positive")
        if self.RAG_MAX_SOURCES <= 0:
            raise ValueError("RAG_MAX_SOURCES must be positive")
        if self.PAYMENT_EVIDENCE_MAX_FILE_SIZE_BYTES <= 0:
            raise ValueError("PAYMENT_EVIDENCE_MAX_FILE_SIZE_BYTES must be positive")
        if not self.SLIP_VERIFICATION_PROVIDER.strip():
            raise ValueError("SLIP_VERIFICATION_PROVIDER must not be empty")
        if self.SLIP_VERIFICATION_TIMEOUT_SECONDS <= 0:
            raise ValueError("SLIP_VERIFICATION_TIMEOUT_SECONDS must be positive")
        if not self.ACTION_COLLECTION_PROVIDER.strip():
            raise ValueError("ACTION_COLLECTION_PROVIDER must not be empty")
        if self.ACTION_COLLECTION_SESSION_TTL_MINUTES <= 0:
            raise ValueError("ACTION_COLLECTION_SESSION_TTL_MINUTES must be positive")
        if not self.GENERATION_PROVIDER.strip():
            raise ValueError("GENERATION_PROVIDER must not be empty")
        if not self.OPENAI_MODEL.strip():
            raise ValueError("OPENAI_MODEL must not be empty")
        if not 0 <= self.GENERATION_TEMPERATURE <= 2:
            raise ValueError("GENERATION_TEMPERATURE must be between 0 and 2")
        if self.GENERATION_MAX_OUTPUT_TOKENS <= 0:
            raise ValueError("GENERATION_MAX_OUTPUT_TOKENS must be positive")
        if self.GENERATION_REQUEST_TIMEOUT_SECONDS <= 0:
            raise ValueError("GENERATION_REQUEST_TIMEOUT_SECONDS must be positive")
        if self.DEMO_CHAT_RATE_LIMIT_REQUESTS <= 0:
            raise ValueError("DEMO_CHAT_RATE_LIMIT_REQUESTS must be positive")
        if self.DEMO_CHAT_RATE_LIMIT_WINDOW_SECONDS <= 0:
            raise ValueError("DEMO_CHAT_RATE_LIMIT_WINDOW_SECONDS must be positive")
        if self.DEMO_CHAT_MAX_INPUT_CHARS <= 0:
            raise ValueError("DEMO_CHAT_MAX_INPUT_CHARS must be positive")
        if not 0 < self.AUTOMATION_WORKER_POLL_SECONDS <= 300:
            raise ValueError("AUTOMATION_WORKER_POLL_SECONDS must be between 0 and 300")
        if not 1 <= self.AUTOMATION_WORKER_BATCH_SIZE <= 500:
            raise ValueError("AUTOMATION_WORKER_BATCH_SIZE must be between 1 and 500")
        if not 0 < self.AUTOMATION_WORKER_HEARTBEAT_SECONDS <= 300:
            raise ValueError(
                "AUTOMATION_WORKER_HEARTBEAT_SECONDS must be between 0 and 300"
            )
        if self.AUTOMATION_WORKER_STALE_SECONDS < (
            self.AUTOMATION_WORKER_HEARTBEAT_SECONDS * 2
        ):
            raise ValueError(
                "AUTOMATION_WORKER_STALE_SECONDS must be at least two "
                "heartbeat intervals"
            )
        if self.AUTOMATION_EXECUTION_STALE_SECONDS <= 0:
            raise ValueError("AUTOMATION_EXECUTION_STALE_SECONDS must be positive")
        if self.AUTOMATION_BACKLOG_ALERT_THRESHOLD_SECONDS <= 0:
            raise ValueError(
                "AUTOMATION_BACKLOG_ALERT_THRESHOLD_SECONDS must be positive"
            )
        if self.AUTOMATION_BACKLOG_ALERT_COUNT <= 0:
            raise ValueError("AUTOMATION_BACKLOG_ALERT_COUNT must be positive")
        if not 5 <= self.PROMOTION_LIFECYCLE_INTERVAL_SECONDS <= 3600:
            raise ValueError(
                "PROMOTION_LIFECYCLE_INTERVAL_SECONDS must be between 5 and 3600"
            )
        if not 1 <= self.PROMOTION_LIFECYCLE_BATCH_SIZE <= 500:
            raise ValueError("PROMOTION_LIFECYCLE_BATCH_SIZE must be between 1 and 500")
        if self.PROMOTION_LIFECYCLE_STALE_SECONDS < (
            self.PROMOTION_LIFECYCLE_INTERVAL_SECONDS * 2
        ):
            raise ValueError(
                "PROMOTION_LIFECYCLE_STALE_SECONDS must be at least two intervals"
            )
        if not 1 <= self.AI_TOOL_MAX_CALLS_PER_TURN <= 3:
            raise ValueError("AI_TOOL_MAX_CALLS_PER_TURN must be between 1 and 3")
        if not 1 <= self.AI_TOOL_CONFIRMATION_TTL_MINUTES <= 60:
            raise ValueError(
                "AI_TOOL_CONFIRMATION_TTL_MINUTES must be between 1 and 60"
            )
        return self

    # ------------------------------------------------------------------ App
    APP_NAME: str = "OneInFlow Platform"
    APP_ENV: str = "development"  # development | staging | production
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:3000"
    TRUSTED_HOSTS: str = "localhost,127.0.0.1,testserver"

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
    QDRANT_KNOWLEDGE_COLLECTION: str = "knowledge_chunks"

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

    # ----------------------------------------------- External channel security
    CHANNEL_CREDENTIAL_ENCRYPTION_KEY: str | None = None
    CHANNEL_CREDENTIAL_KEY_VERSION: str = "v1"
    CHANNEL_PROVIDER_TIMEOUT_SECONDS: float = 10.0
    CHANNEL_WEBHOOK_MAX_BYTES: int = 1_000_000

    # ---------------------------------------------- Automation worker operations
    AUTOMATION_WORKER_POLL_SECONDS: float = 5.0
    AUTOMATION_WORKER_BATCH_SIZE: int = 20
    AUTOMATION_WORKER_HEARTBEAT_SECONDS: float = 15.0
    AUTOMATION_WORKER_STALE_SECONDS: int = 45
    AUTOMATION_EXECUTION_STALE_SECONDS: int = 300
    AUTOMATION_BACKLOG_ALERT_THRESHOLD_SECONDS: int = 300
    AUTOMATION_BACKLOG_ALERT_COUNT: int = 1000
    AUTOMATION_WORKER_BUILD_IDENTIFIER: str | None = None
    # Scheduled campaign lifecycle runs inside the supervised automation worker.
    PROMOTION_LIFECYCLE_ENABLED: bool = True
    PROMOTION_LIFECYCLE_INTERVAL_SECONDS: int = 60
    PROMOTION_LIFECYCLE_BATCH_SIZE: int = 100
    PROMOTION_LIFECYCLE_STALE_SECONDS: int = 300

    # ------------------------------------------------ AI action orchestration
    AI_TOOL_MAX_CALLS_PER_TURN: int = 3
    AI_TOOL_CONFIRMATION_TTL_MINUTES: int = 10

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

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [item.strip() for item in self.TRUSTED_HOSTS.split(",") if item.strip()]


def validate_production_settings(settings: Settings) -> None:
    """Fail startup closed on unsafe production-only configuration."""
    if settings.APP_ENV != "production":
        return
    errors: list[str] = []
    if settings.DEBUG:
        errors.append("DEBUG must be false")
    if len(settings.JWT_SECRET_KEY.encode()) < 32:
        errors.append("JWT_SECRET_KEY must contain at least 32 bytes")
    if not settings.OTP_HASH_SECRET or len(settings.OTP_HASH_SECRET.encode()) < 32:
        errors.append("OTP_HASH_SECRET must contain at least 32 bytes")
    if "*" in settings.cors_origins or not settings.cors_origins:
        errors.append("CORS_ORIGINS must contain explicit origins")
    if "*" in settings.trusted_hosts or not settings.trusted_hosts:
        errors.append("TRUSTED_HOSTS must contain explicit hosts")
    if settings.EMAIL_PROVIDER.strip().lower() == "development":
        errors.append("EMAIL_PROVIDER cannot be development")
    if settings.GENERATION_PROVIDER.strip().lower() == "development":
        errors.append("GENERATION_PROVIDER cannot be development")
    if settings.EMBEDDING_PROVIDER.strip().lower() == "development":
        errors.append("EMBEDDING_PROVIDER cannot be development")
    if settings.ACTION_COLLECTION_PROVIDER.strip().lower() != "generation":
        errors.append("ACTION_COLLECTION_PROVIDER must be generation")
    if settings.SLIP_VERIFICATION_PROVIDER.strip().lower() == "development":
        errors.append("SLIP_VERIFICATION_PROVIDER cannot be development")
    if errors:
        raise ValueError("Unsafe production configuration: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
