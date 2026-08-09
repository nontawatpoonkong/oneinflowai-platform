"""Atomic persistence operations for knowledge chunks."""

import uuid

from sqlalchemy import delete, select

from app.models.knowledge_chunk import KnowledgeChunk
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
