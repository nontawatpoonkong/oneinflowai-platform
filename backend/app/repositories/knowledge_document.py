"""Knowledge document persistence."""

import uuid

from sqlalchemy import func, select

from app.models.knowledge_document import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
)
from app.repositories.base import BaseRepository


class KnowledgeDocumentRepository(BaseRepository[KnowledgeDocument]):
    model = KnowledgeDocument

    async def get_for_workspace(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> KnowledgeDocument | None:
        result = await self.session.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.workspace_id == workspace_id,
                KnowledgeDocument.status != KnowledgeDocumentStatus.DELETED,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_workspace(
        self, workspace_id: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[KnowledgeDocument], int]:
        filters = (
            KnowledgeDocument.workspace_id == workspace_id,
            KnowledgeDocument.status != KnowledgeDocumentStatus.DELETED,
        )
        total = await self.session.scalar(
            select(func.count(KnowledgeDocument.id)).where(*filters)
        )
        result = await self.session.execute(
            select(KnowledgeDocument)
            .where(*filters)
            .order_by(KnowledgeDocument.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)
