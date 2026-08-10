"""Workspace-safe semantic retrieval with PostgreSQL as source of truth."""

import time
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AppError,
    EmbeddingProviderError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentNotIndexedError,
    KnowledgeRetrievalError,
    KnowledgeRetrievalValidationError,
)
from app.core.logging import get_logger
from app.integrations.embedding import EmbeddingProvider, create_embedding_provider
from app.integrations.qdrant_knowledge import KnowledgeVectorStore
from app.models.knowledge_document import KnowledgeDocumentStatus, KnowledgeIndexStatus
from app.repositories.knowledge_chunk import KnowledgeChunkRepository
from app.repositories.knowledge_document import KnowledgeDocumentRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    text: str
    score: float
    content_hash: str
    chunking_version: str
    embedding_model: str
    embedding_version: str
    document_title: str | None = None
    original_filename: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalResponse:
    query: str
    results: list[RetrievalResult]


class KnowledgeRetrievalService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        vector_store: KnowledgeVectorStore,
        provider: EmbeddingProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or create_embedding_provider(self.settings)
        self.vector_store = vector_store
        self.documents = KnowledgeDocumentRepository(session)
        self.chunks = KnowledgeChunkRepository(session)

    async def search(
        self,
        *,
        workspace_id: uuid.UUID,
        query: str,
        limit: int | None = None,
        document_id: uuid.UUID | None = None,
    ) -> RetrievalResponse:
        started = time.perf_counter()
        normalized_query = query.strip()
        if not normalized_query:
            raise KnowledgeRetrievalValidationError("Search query must not be empty")
        if (
            len(normalized_query)
            > self.settings.KNOWLEDGE_RETRIEVAL_MAX_QUERY_CHARACTERS
        ):
            raise KnowledgeRetrievalValidationError("Search query is too long")
        effective_limit = limit or self.settings.KNOWLEDGE_RETRIEVAL_DEFAULT_LIMIT
        if (
            effective_limit <= 0
            or effective_limit > self.settings.KNOWLEDGE_RETRIEVAL_MAX_LIMIT
        ):
            raise KnowledgeRetrievalValidationError("Search result limit is invalid")

        if document_id is not None:
            document = await self.documents.get_for_workspace(workspace_id, document_id)
            if document is None:
                raise KnowledgeDocumentNotFoundError()
            if (
                document.status is not KnowledgeDocumentStatus.READY
                or document.index_status is not KnowledgeIndexStatus.INDEXED
            ):
                raise KnowledgeDocumentNotIndexedError()

        embedding = await self.provider.embed_texts([normalized_query])
        if (
            len(embedding.vectors) != 1
            or embedding.dimensions <= 0
            or len(embedding.vectors[0]) != embedding.dimensions
        ):
            raise EmbeddingProviderError("Query embedding response is invalid")
        try:
            await self.vector_store.validate_collection(embedding.dimensions)
            hits = await self.vector_store.search(
                vector=embedding.vectors[0],
                workspace_id=workspace_id,
                document_id=document_id,
                embedding_model=embedding.model,
                embedding_version=self.provider.embedding_version,
                limit=effective_limit,
                score_threshold=self.settings.KNOWLEDGE_RETRIEVAL_SCORE_THRESHOLD,
            )
        except AppError:
            raise
        except Exception as exc:
            raise KnowledgeRetrievalError() from exc

        rows = await self.chunks.get_with_documents({hit.point_id for hit in hits})
        trusted = {chunk.id: (chunk, document) for chunk, document in rows}
        results: list[RetrievalResult] = []
        for hit in hits:
            candidate = trusted.get(hit.point_id)
            if candidate is None:
                continue
            chunk, document = candidate
            payload = hit.payload
            if (
                chunk.workspace_id != workspace_id
                or document.workspace_id != workspace_id
                or document.status is not KnowledgeDocumentStatus.READY
                or document.index_status is not KnowledgeIndexStatus.INDEXED
                or chunk.embedding_model != embedding.model
                or chunk.embedding_version != self.provider.embedding_version
                or payload.get("workspace_id") != str(workspace_id)
                or payload.get("chunk_id") != str(chunk.id)
                or payload.get("document_id") != str(document.id)
                or payload.get("embedding_model") != embedding.model
                or payload.get("embedding_version") != self.provider.embedding_version
                or (document_id is not None and document.id != document_id)
            ):
                continue
            results.append(
                RetrievalResult(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    score=hit.score,
                    content_hash=chunk.content_hash,
                    chunking_version=chunk.chunking_version,
                    embedding_model=chunk.embedding_model,
                    embedding_version=chunk.embedding_version,
                    document_title=document.title,
                    original_filename=document.original_filename,
                )
            )
        logger.info(
            "knowledge_retrieval_completed",
            extra={
                "workspace_id": str(workspace_id),
                "document_id": str(document_id) if document_id else None,
                "query_character_count": len(normalized_query),
                "result_count": len(results),
                "provider": self.provider.name,
                "model": embedding.model,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return RetrievalResponse(query=normalized_query, results=results)
