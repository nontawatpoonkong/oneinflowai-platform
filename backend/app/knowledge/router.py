"""Workspace-scoped knowledge document routes."""

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.knowledge_document import KnowledgeDocument
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.knowledge import (
    KnowledgeDocumentContentResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
)
from app.schemas.response import success_response
from app.services.knowledge_document import KnowledgeDocumentService
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


@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    document = await KnowledgeDocumentService(session).get(
        workspace.id, document_id
    )
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


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await KnowledgeDocumentService(session).delete(workspace.id, document_id)
    return success_response(message="Document deleted")
