"""Provider-neutral embedding integrations."""

from app.integrations.embedding.base import EmbeddingBatchResult, EmbeddingProvider
from app.integrations.embedding.development import DevelopmentEmbeddingProvider
from app.integrations.embedding.factory import create_embedding_provider
from app.integrations.embedding.openai import OpenAIEmbeddingProvider

__all__ = [
    "DevelopmentEmbeddingProvider",
    "EmbeddingBatchResult",
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "create_embedding_provider",
]
