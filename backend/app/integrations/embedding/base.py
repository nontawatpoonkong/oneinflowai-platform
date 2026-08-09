"""Embedding provider contracts."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    vectors: list[list[float]]
    model: str
    dimensions: int
    token_usage: int | None = None


class EmbeddingProvider(Protocol):
    name: str
    embedding_version: str

    async def embed_texts(self, texts: list[str]) -> EmbeddingBatchResult: ...
