"""Deterministic embedding provider contract tests without network access."""

from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from app.core.config import Settings
from app.core.exceptions import EmbeddingConfigurationError, EmbeddingProviderError
from app.integrations.embedding import (
    DevelopmentEmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
)


class FakeEmbeddingsAPI:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _response(vectors: list[list[float]], *, indexes: list[int] | None = None):
    indexes = indexes or list(range(len(vectors)))
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=index, embedding=vector)
            for index, vector in zip(indexes, vectors, strict=True)
        ],
        model="text-embedding-3-small",
        usage=SimpleNamespace(total_tokens=7),
    )


def _provider(api: FakeEmbeddingsAPI) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        timeout_seconds=3,
        client=SimpleNamespace(embeddings=api),
    )


async def test_development_provider_is_deterministic_fixed_dimension() -> None:
    provider = DevelopmentEmbeddingProvider(dimensions=12)
    first = await provider.embed_texts(["same", "changed"])
    second = await provider.embed_texts(["same"])
    assert first.vectors[0] == second.vectors[0]
    assert first.vectors[0] != first.vectors[1]
    assert first.dimensions == 12
    assert all(len(vector) == 12 for vector in first.vectors)


async def test_development_provider_rejects_empty_input() -> None:
    provider = DevelopmentEmbeddingProvider()
    with pytest.raises(ValueError):
        await provider.embed_texts([])
    with pytest.raises(ValueError):
        await provider.embed_texts([""])


async def test_openai_provider_preserves_order_model_and_usage() -> None:
    api = FakeEmbeddingsAPI(_response([[2.0, 2.0], [1.0, 1.0]], indexes=[1, 0]))
    result = await _provider(api).embed_texts(["first", "second"])
    assert result.vectors == [[1.0, 1.0], [2.0, 2.0]]
    assert result.model == "text-embedding-3-small"
    assert result.token_usage == 7
    assert api.calls == [
        {"input": ["first", "second"], "model": "text-embedding-3-small"}
    ]


async def test_openai_provider_rejects_count_and_dimension_mismatch() -> None:
    with pytest.raises(EmbeddingProviderError, match="count mismatch"):
        await _provider(FakeEmbeddingsAPI(_response([[1.0]]))).embed_texts(["a", "b"])
    with pytest.raises(EmbeddingProviderError, match="dimensions"):
        await _provider(FakeEmbeddingsAPI(_response([[1.0], [1.0, 2.0]]))).embed_texts(
            ["a", "b"]
        )


@pytest.mark.parametrize(
    "error",
    [
        AuthenticationError(
            "bad key",
            response=httpx.Response(401, request=httpx.Request("POST", "https://test")),
            body=None,
        ),
        RateLimitError(
            "limited",
            response=httpx.Response(429, request=httpx.Request("POST", "https://test")),
            body=None,
        ),
        APIConnectionError(request=httpx.Request("POST", "https://test")),
        APITimeoutError(request=httpx.Request("POST", "https://test")),
        APIStatusError(
            "server",
            response=httpx.Response(500, request=httpx.Request("POST", "https://test")),
            body=None,
        ),
    ],
)
async def test_openai_provider_maps_sdk_failures(error: Exception) -> None:
    with pytest.raises(EmbeddingProviderError):
        await _provider(FakeEmbeddingsAPI(error=error)).embed_texts(["safe text"])


def test_embedding_factory_validates_configuration() -> None:
    development = create_embedding_provider(
        Settings(_env_file=None, EMBEDDING_PROVIDER="development")
    )
    assert isinstance(development, DevelopmentEmbeddingProvider)
    with pytest.raises(EmbeddingConfigurationError):
        create_embedding_provider(
            Settings(_env_file=None, EMBEDDING_PROVIDER="openai", OPENAI_API_KEY=None)
        )
    with pytest.raises(EmbeddingConfigurationError):
        create_embedding_provider(
            Settings(_env_file=None, EMBEDDING_PROVIDER="unknown")
        )
