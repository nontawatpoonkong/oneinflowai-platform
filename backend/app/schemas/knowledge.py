"""Knowledge document API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.knowledge_document import (
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
)


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    original_filename: str
    mime_type: str
    file_size: int
    source_type: KnowledgeSourceType
    status: KnowledgeDocumentStatus
    language: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
