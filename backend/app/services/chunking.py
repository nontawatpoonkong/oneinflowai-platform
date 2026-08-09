"""Chunk computation and transaction-safe persistence orchestration."""

import hashlib
import time
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking import RecursiveTextChunker
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    KnowledgeChunkingFailedError,
    KnowledgeDocumentNotFoundError,
)
from app.core.logging import get_logger
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocumentStatus
from app.repositories.knowledge_chunk import KnowledgeChunkRepository
from app.repositories.knowledge_document import KnowledgeDocumentRepository
from app.repositories.knowledge_document_content import (
    KnowledgeDocumentContentRepository,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChunkingResult:
    chunk_count: int
    chunking_version: str


class ChunkingService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.documents = KnowledgeDocumentRepository(session)
        self.contents = KnowledgeDocumentContentRepository(session)
        self.chunks = KnowledgeChunkRepository(session)

    async def chunk_document(
        self, document_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> ChunkingResult:
        started = time.perf_counter()
        document = await self.documents.get_for_workspace(workspace_id, document_id)
        if document is None:
            raise KnowledgeDocumentNotFoundError()
        content = await self.contents.get_by_document_id(document.id)
        if content is None or not content.extracted_text:
            raise KnowledgeChunkingFailedError("Extracted document content is empty")

        strategy = RecursiveTextChunker(
            chunk_size=self.settings.KNOWLEDGE_CHUNK_SIZE,
            overlap=self.settings.KNOWLEDGE_CHUNK_OVERLAP,
            max_chunks=self.settings.KNOWLEDGE_MAX_CHUNKS_PER_DOCUMENT,
        )
        try:
            generated = strategy.chunk(content.extracted_text)
        except ValueError as exc:
            raise KnowledgeChunkingFailedError(str(exc)) from exc
        rows = [
            KnowledgeChunk(
                document_id=document.id,
                content_id=content.id,
                workspace_id=document.workspace_id,
                chunk_index=index,
                text=chunk.text,
                character_count=len(chunk.text),
                token_count=None,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                chunking_version=strategy.version,
                content_hash=hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
            )
            for index, chunk in enumerate(generated)
        ]
        try:
            await self.chunks.replace(content.id, rows)
            document.status = KnowledgeDocumentStatus.READY
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        logger.info(
            "knowledge_chunking_completed",
            extra={
                "document_id": str(document.id),
                "workspace_id": str(document.workspace_id),
                "chunk_count": len(rows),
                "chunking_version": strategy.version,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return ChunkingResult(len(rows), strategy.version)

    async def list_chunks(
        self, document_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[KnowledgeChunk]:
        document = await self.documents.get_for_workspace(workspace_id, document_id)
        if document is None:
            raise KnowledgeDocumentNotFoundError()
        content = await self.contents.get_by_document_id(document.id)
        if content is None:
            raise KnowledgeDocumentNotFoundError()
        return await self.chunks.list_for_content(content.id)
