"""Atomic persistence operations for knowledge chunks."""

import uuid

from sqlalchemy import delete, select

from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.repositories.base import BaseRepository


class KnowledgeChunkRepository(BaseRepository[KnowledgeChunk]):
    model = KnowledgeChunk

    async def list_for_content(self, content_id: uuid.UUID) -> list[KnowledgeChunk]:
        result = await self.session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.content_id == content_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def replace(
        self, content_id: uuid.UUID, chunks: list[KnowledgeChunk]
    ) -> None:
        await self.session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.content_id == content_id)
        )
        self.session.add_all(chunks)
        await self.session.flush()

    async def get_with_documents(
        self, chunk_ids: set[uuid.UUID]
    ) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
        if not chunk_ids:
            return []
        result = await self.session.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeChunk.id.in_(chunk_ids))
        )
        return list(result.tuples().all())
