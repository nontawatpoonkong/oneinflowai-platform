"""Knowledge document API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.knowledge_document import (
    KnowledgeDocumentStatus,
    KnowledgeIndexStatus,
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
    index_status: KnowledgeIndexStatus
    indexed_at: datetime | None
    index_error_code: str | None
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


class KnowledgeDocumentContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    extracted_text: str
    character_count: int
    word_count: int
    extraction_method: str
    extraction_version: str
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    text: str
    character_count: int
    token_count: int | None
    start_offset: int
    end_offset: int
    chunking_version: str
    content_hash: str


class KnowledgeRechunkResponse(BaseModel):
    chunk_count: int
    chunking_version: str


class KnowledgeIndexResponse(BaseModel):
    document_id: uuid.UUID
    index_status: KnowledgeIndexStatus
    chunk_count: int
    embedding_model: str
    indexed_at: datetime
    embedding_request_count: int


class KnowledgeSearchRequest(BaseModel):
    query: str
    limit: int | None = None
    document_id: uuid.UUID | None = None


class KnowledgeRetrievalResultResponse(BaseModel):
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


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[KnowledgeRetrievalResultResponse]
