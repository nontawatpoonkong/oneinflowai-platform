"""Extracted knowledge content persistence."""

import uuid

from sqlalchemy import select

from app.document_parsers.base import ExtractionOutput
from app.models.knowledge_document_content import KnowledgeDocumentContent
from app.repositories.base import BaseRepository


class KnowledgeDocumentContentRepository(BaseRepository[KnowledgeDocumentContent]):
    model = KnowledgeDocumentContent

    async def get_by_document_id(
        self, document_id: uuid.UUID
    ) -> KnowledgeDocumentContent | None:
        result = await self.session.execute(
            select(KnowledgeDocumentContent).where(
                KnowledgeDocumentContent.document_id == document_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, document_id: uuid.UUID, output: ExtractionOutput
    ) -> KnowledgeDocumentContent:
        content = await self.get_by_document_id(document_id)
        if content is None:
            content = KnowledgeDocumentContent(document_id=document_id)
            self.session.add(content)
        content.extracted_text = output.text
        content.character_count = output.character_count
        content.word_count = output.word_count
        content.extraction_method = output.method
        content.extraction_version = output.version
        await self.session.flush()
        return content
