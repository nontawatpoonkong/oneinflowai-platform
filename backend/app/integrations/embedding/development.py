"""Deterministic non-semantic embeddings for local development and tests."""

import hashlib
import struct

from app.integrations.embedding.base import EmbeddingBatchResult


class DevelopmentEmbeddingProvider:
    name = "development"

    def __init__(self, *, dimensions: int = 8) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be greater than zero")
        self.dimensions = dimensions
        self.embedding_version = f"development:sha256:{dimensions}:v1"

    async def embed_texts(self, texts: list[str]) -> EmbeddingBatchResult:
        if not texts or any(not text for text in texts):
            raise ValueError("embedding input must contain non-empty texts")
        vectors = [self._vector(text) for text in texts]
        return EmbeddingBatchResult(
            vectors=vectors,
            model="development-sha256",
            dimensions=self.dimensions,
        )

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        output: list[float] = []
        counter = 0
        while len(output) < self.dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for offset in range(0, len(digest), 4):
                value = struct.unpack(">I", digest[offset : offset + 4])[0]
                output.append((value / 0xFFFFFFFF) * 2 - 1)
                if len(output) == self.dimensions:
                    break
            counter += 1
        return output
