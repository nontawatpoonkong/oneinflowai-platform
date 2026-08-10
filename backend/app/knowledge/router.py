"""Workspace-scoped knowledge document routes."""

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.database.session import get_db
from app.integrations.embedding import create_embedding_provider
from app.integrations.qdrant_knowledge import QdrantKnowledgeVectorStore
from app.models.knowledge_document import KnowledgeDocument
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.knowledge import (
    KnowledgeChunkResponse,
    KnowledgeDocumentContentResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeIndexResponse,
    KnowledgeRechunkResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    RAGPreviewResponse,
)
from app.schemas.response import success_response
from app.services.chunking import ChunkingService
from app.services.knowledge_document import KnowledgeDocumentService
from app.services.knowledge_indexing import KnowledgeIndexingService
from app.services.knowledge_retrieval import KnowledgeRetrievalService
from app.services.rag_preparation import RAGPreparationService
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


def _document_data(document: KnowledgeDocument) -> dict:
    return KnowledgeDocumentResponse.model_validate(document).model_dump(mode="json")


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    language: str | None = Form(default=None, max_length=16),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    document = await KnowledgeDocumentService(session).upload(
        workspace_id=workspace.id,
        created_by=user.id,
        file=file,
        title=title,
        language=language,
    )
    return success_response(data=_document_data(document), message="Document uploaded")


@router.get("")
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await KnowledgeDocumentService(session).list(
        workspace.id, page=page, page_size=page_size
    )
    data = KnowledgeDocumentListResponse(
        items=[KnowledgeDocumentResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )
    return success_response(data=data.model_dump(mode="json"), message="OK")


@router.post("/search")
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    request: Request,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    service = KnowledgeRetrievalService(
        session,
        settings=settings,
        provider=create_embedding_provider(settings),
        vector_store=QdrantKnowledgeVectorStore(
            request.app.state.qdrant,
            collection_name=settings.QDRANT_KNOWLEDGE_COLLECTION,
        ),
    )
    result = await service.search(
        workspace_id=workspace.id,
        query=payload.query,
        limit=payload.limit,
        document_id=payload.document_id,
    )
    data = KnowledgeSearchResponse.model_validate(result, from_attributes=True)
    return success_response(data=data.model_dump(mode="json"), message="OK")


@router.post("/rag-preview")
async def preview_rag(
    payload: KnowledgeSearchRequest,
    request: Request,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Prepare bounded RAG context and prompts without calling a generation model."""
    settings = get_settings()
    retrieval = KnowledgeRetrievalService(
        session,
        settings=settings,
        provider=create_embedding_provider(settings),
        vector_store=QdrantKnowledgeVectorStore(
            request.app.state.qdrant,
            collection_name=settings.QDRANT_KNOWLEDGE_COLLECTION,
        ),
    )
    package = await RAGPreparationService(retrieval, settings=settings).prepare(
        workspace_id=workspace.id,
        query=payload.query,
        limit=payload.limit,
        document_id=payload.document_id,
    )
    context = package.context
    data = RAGPreviewResponse(
        query=context.query,
        sources=context.sources,
        formatted_context=context.formatted_context,
        included_chunk_count=context.included_chunk_count,
        omitted_chunk_count=context.omitted_chunk_count,
        character_count=context.character_count,
        context_version=context.version,
        user_prompt=package.user_prompt,
        prompt_version=package.version,
    )
    return success_response(data=data.model_dump(mode="json"), message="OK")


@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    document = await KnowledgeDocumentService(session).get(workspace.id, document_id)
    return success_response(data=_document_data(document), message="OK")


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    content = await KnowledgeDocumentService(session).get_content(
        workspace.id, document_id
    )
    data = KnowledgeDocumentContentResponse.model_validate(content).model_dump(
        mode="json"
    )
    return success_response(data=data, message="OK")


@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    chunks = await ChunkingService(session).list_chunks(document_id, workspace.id)
    data = [
        KnowledgeChunkResponse.model_validate(chunk).model_dump(mode="json")
        for chunk in chunks
    ]
    return success_response(data=data, message="OK")


@router.post("/{document_id}/rechunk")
async def rechunk_document(
    document_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    result = await ChunkingService(session).chunk_document(document_id, workspace.id)
    data = KnowledgeRechunkResponse(
        chunk_count=result.chunk_count,
        chunking_version=result.chunking_version,
    )
    return success_response(
        data=data.model_dump(mode="json"), message="Document rechunked"
    )


@router.post("/{document_id}/index")
async def index_document(
    document_id: uuid.UUID,
    request: Request,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    service = KnowledgeIndexingService(
        session,
        settings=settings,
        provider=create_embedding_provider(settings),
        vector_store=QdrantKnowledgeVectorStore(
            request.app.state.qdrant,
            collection_name=settings.QDRANT_KNOWLEDGE_COLLECTION,
        ),
    )
    result = await service.index_document(document_id, workspace.id)
    data = KnowledgeIndexResponse(
        document_id=result.document_id,
        index_status="INDEXED",
        chunk_count=result.chunk_count,
        embedding_model=result.embedding_model,
        indexed_at=result.indexed_at,
        embedding_request_count=result.embedding_request_count,
    )
    return success_response(
        data=data.model_dump(mode="json"), message="Document indexed"
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await KnowledgeDocumentService(session).delete(workspace.id, document_id)
    return success_response(message="Document deleted")
