"""Embedding provider factory."""

from app.core.config import Settings, get_settings
from app.core.exceptions import EmbeddingConfigurationError
from app.integrations.embedding.base import EmbeddingProvider
from app.integrations.embedding.development import DevelopmentEmbeddingProvider
from app.integrations.embedding.openai import OpenAIEmbeddingProvider


def create_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    configured = settings or get_settings()
    provider = configured.EMBEDDING_PROVIDER.lower().strip()
    if provider == "development":
        return DevelopmentEmbeddingProvider()
    if provider == "openai":
        if not configured.OPENAI_API_KEY:
            raise EmbeddingConfigurationError()
        return OpenAIEmbeddingProvider(
            api_key=configured.OPENAI_API_KEY,
            model=configured.OPENAI_EMBEDDING_MODEL,
            timeout_seconds=configured.EMBEDDING_REQUEST_TIMEOUT_SECONDS,
        )
    raise EmbeddingConfigurationError()
