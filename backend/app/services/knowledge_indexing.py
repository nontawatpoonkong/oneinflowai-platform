"""Explicit knowledge embedding and vector-index synchronization."""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from qdrant_client import models
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AppError,
    EmbeddingProviderError,
    KnowledgeDocumentNotFoundError,
    KnowledgeIndexingError,
    KnowledgeIndexingNotEligibleError,
)
from app.core.logging import get_logger
from app.integrations.embedding import EmbeddingProvider, create_embedding_provider
from app.integrations.qdrant_knowledge import KnowledgeVectorStore
from app.models.audit import AuditActorType, AuditArea
from app.models.knowledge_document import (
    KnowledgeDocumentStatus,
    KnowledgeIndexStatus,
)
from app.repositories.knowledge_chunk import KnowledgeChunkRepository
from app.repositories.knowledge_document import KnowledgeDocumentRepository
from app.repositories.knowledge_document_content import (
    KnowledgeDocumentContentRepository,
)
from app.services.audit import AuditService, current_actor_user_id

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class KnowledgeIndexingResult:
    document_id: uuid.UUID
    chunk_count: int
    embedding_model: str
    indexed_at: datetime
    embedding_request_count: int


class KnowledgeIndexingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        vector_store: KnowledgeVectorStore,
        provider: EmbeddingProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.provider = provider or create_embedding_provider(self.settings)
        self.vector_store = vector_store
        self.documents = KnowledgeDocumentRepository(session)
        self.contents = KnowledgeDocumentContentRepository(session)
        self.chunks = KnowledgeChunkRepository(session)

    async def index_document(
        self, document_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> KnowledgeIndexingResult:
        started = time.perf_counter()
        document = await self.documents.get_for_workspace(workspace_id, document_id)
        if document is None:
            raise KnowledgeDocumentNotFoundError()
        if document.status is not KnowledgeDocumentStatus.READY:
            raise KnowledgeIndexingNotEligibleError()
        content = await self.contents.get_by_document_id(document.id)
        if content is None:
            raise KnowledgeIndexingNotEligibleError()
        chunks = await self.chunks.list_for_content(content.id)
        if not chunks or any(not chunk.text for chunk in chunks):
            raise KnowledgeIndexingNotEligibleError()

        document.index_status = KnowledgeIndexStatus.INDEXING
        document.index_error_code = None
        AuditService(self.session).record(
            workspace_id=workspace_id,
            actor_user_id=current_actor_user_id(),
            actor_type=(
                AuditActorType.USER
                if current_actor_user_id()
                else AuditActorType.SYSTEM
            ),
            action="REINDEX_REQUESTED",
            area=AuditArea.KNOWLEDGE,
            resource_type="KnowledgeDocument",
            resource_id=document.id,
        )
        await self.session.commit()
        try:
            vectors: list[list[float]] = []
            embedding_model: str | None = None
            dimensions: int | None = None
            request_count = 0
            batch_size = self.settings.EMBEDDING_BATCH_SIZE
            for offset in range(0, len(chunks), batch_size):
                batch = chunks[offset : offset + batch_size]
                result = await self.provider.embed_texts(
                    [chunk.text for chunk in batch]
                )
                request_count += 1
                if len(result.vectors) != len(batch):
                    raise EmbeddingProviderError("Embedding response count mismatch")
                if result.dimensions <= 0 or any(
                    len(vector) != result.dimensions for vector in result.vectors
                ):
                    raise EmbeddingProviderError(
                        "Embedding vector dimensions are inconsistent"
                    )
                if dimensions is not None and dimensions != result.dimensions:
                    raise EmbeddingProviderError(
                        "Embedding vector dimensions are inconsistent"
                    )
                if embedding_model is not None and embedding_model != result.model:
                    raise EmbeddingProviderError(
                        "Embedding model changed across batches"
                    )
                dimensions = result.dimensions
                embedding_model = result.model
                vectors.extend(result.vectors)
            if (
                len(vectors) != len(chunks)
                or dimensions is None
                or embedding_model is None
            ):
                raise EmbeddingProviderError("Embedding response count mismatch")

            await self.vector_store.ensure_collection(dimensions)
            previous_ids = await self.vector_store.current_point_ids(
                document.workspace_id, document.id
            )
            points = [
                models.PointStruct(
                    id=chunk.id,
                    vector=vector,
                    payload={
                        "workspace_id": str(document.workspace_id),
                        "document_id": str(document.id),
                        "content_id": str(content.id),
                        "chunk_id": str(chunk.id),
                        "chunk_index": chunk.chunk_index,
                        "content_hash": chunk.content_hash,
                        "chunking_version": chunk.chunking_version,
                        "embedding_model": embedding_model,
                        "embedding_version": self.provider.embedding_version,
                    },
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
            await self.vector_store.upsert(points)
            current_ids = {chunk.id for chunk in chunks}
            await self.vector_store.delete_ids(previous_ids - current_ids)

            indexed_at = datetime.now(UTC)
            for chunk in chunks:
                chunk.embedding_model = embedding_model
                chunk.embedding_version = self.provider.embedding_version
                chunk.indexed_at = indexed_at
            document.index_status = KnowledgeIndexStatus.INDEXED
            document.indexed_at = indexed_at
            document.index_error_code = None
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            refreshed = await self.documents.get_for_workspace(
                workspace_id, document_id
            )
            if refreshed is not None:
                refreshed.index_status = KnowledgeIndexStatus.FAILED
                refreshed.index_error_code = self._safe_error_code(exc)
                await self.session.commit()
            if isinstance(exc, AppError):
                raise
            raise KnowledgeIndexingError() from exc

        logger.info(
            "knowledge_indexing_completed",
            extra={
                "workspace_id": str(document.workspace_id),
                "document_id": str(document.id),
                "chunk_count": len(chunks),
                "provider": self.provider.name,
                "model": embedding_model,
                "dimensions": dimensions,
                "request_batch_count": request_count,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return KnowledgeIndexingResult(
            document_id=document.id,
            chunk_count=len(chunks),
            embedding_model=embedding_model,
            indexed_at=indexed_at,
            embedding_request_count=request_count,
        )

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        if isinstance(exc, AppError):
            return exc.code[:64]
        return "KNOWLEDGE_INDEXING_FAILED"
