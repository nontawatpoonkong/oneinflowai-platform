"""Official async OpenAI embedding provider adapter."""

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from app.core.exceptions import EmbeddingProviderError
from app.integrations.embedding.base import EmbeddingBatchResult


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: AsyncOpenAI | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")
        if not model:
            raise ValueError("OPENAI_EMBEDDING_MODEL is required")
        if timeout_seconds <= 0:
            raise ValueError("embedding timeout must be greater than zero")
        self.model = model
        self.embedding_version = f"openai:{model}:v1"
        self.client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def embed_texts(self, texts: list[str]) -> EmbeddingBatchResult:
        if not texts or any(not text for text in texts):
            raise ValueError("embedding input must contain non-empty texts")
        try:
            response = await self.client.embeddings.create(
                input=texts, model=self.model
            )
        except (
            AuthenticationError,
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
            APIStatusError,
        ) as exc:
            raise EmbeddingProviderError() from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(texts):
            raise EmbeddingProviderError("Embedding response count mismatch")
        dimensions = len(vectors[0]) if vectors else 0
        if dimensions <= 0 or any(len(vector) != dimensions for vector in vectors):
            raise EmbeddingProviderError("Embedding vector dimensions are inconsistent")
        usage = getattr(response, "usage", None)
        return EmbeddingBatchResult(
            vectors=vectors,
            model=response.model,
            dimensions=dimensions,
            token_usage=getattr(usage, "total_tokens", None),
        )
