"""Knowledge document metadata and storage orchestration."""

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    InvalidKnowledgeFileError,
    KnowledgeDocumentNotFoundError,
    KnowledgeFileTooLargeError,
)
from app.models.knowledge_document import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
)
from app.repositories.knowledge_document import KnowledgeDocumentRepository
from app.storage import StorageProvider, create_storage_provider

_ALLOWED_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain", "text/x-markdown"},
}


class KnowledgeDocumentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: StorageProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.storage = storage or create_storage_provider(self.settings)
        self.documents = KnowledgeDocumentRepository(session)

    async def upload(
        self,
        *,
        workspace_id: uuid.UUID,
        created_by: uuid.UUID,
        file: UploadFile,
        title: str | None,
        language: str | None,
    ) -> KnowledgeDocument:
        filename = Path(file.filename or "").name
        extension = Path(filename).suffix.lower()
        content_type = (file.content_type or "").lower()
        if not filename or extension not in _ALLOWED_TYPES:
            raise InvalidKnowledgeFileError()
        if content_type not in _ALLOWED_TYPES[extension]:
            raise InvalidKnowledgeFileError()

        maximum = self.settings.KNOWLEDGE_MAX_FILE_SIZE_BYTES
        data = await file.read(maximum + 1)
        if len(data) > maximum:
            raise KnowledgeFileTooLargeError()
        if not data:
            raise InvalidKnowledgeFileError()

        document_id = uuid.uuid4()
        storage_key = f"{workspace_id}/{document_id}{extension}"
        document = KnowledgeDocument(
            id=document_id,
            workspace_id=workspace_id,
            title=(title or Path(filename).stem).strip()[:255],
            original_filename=filename[:255],
            storage_key=storage_key,
            mime_type=content_type,
            file_size=len(data),
            source_type=KnowledgeSourceType.UPLOAD,
            status=KnowledgeDocumentStatus.UPLOADING,
            language=(language.strip()[:16] if language and language.strip() else None),
            created_by=created_by,
        )
        await self.documents.add(document)
        try:
            await self.storage.save(key=storage_key, data=data)
            document.status = KnowledgeDocumentStatus.READY
            await self.session.commit()
            await self.session.refresh(document)
            return document
        except Exception:
            await self.session.rollback()
            await self.storage.delete(key=storage_key)
            raise

    async def list(
        self, workspace_id: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[KnowledgeDocument], int]:
        return await self.documents.list_for_workspace(
            workspace_id, page=page, page_size=page_size
        )

    async def get(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> KnowledgeDocument:
        document = await self.documents.get_for_workspace(workspace_id, document_id)
        if document is None:
            raise KnowledgeDocumentNotFoundError()
        return document

    async def delete(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> None:
        document = await self.get(workspace_id, document_id)
        await self.storage.delete(key=document.storage_key)
        document.status = KnowledgeDocumentStatus.DELETED
        await self.session.commit()
