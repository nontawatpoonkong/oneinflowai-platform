"""Knowledge document metadata and storage orchestration."""

import uuid
from contextlib import suppress
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

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
_READ_CHUNK_SIZE = 64 * 1024
_DOCX_REQUIRED_MEMBERS = {"[Content_Types].xml", "word/document.xml"}


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

        data = await self._read_limited(file)
        if not data:
            raise InvalidKnowledgeFileError()
        self._validate_signature(extension, data)

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
            with suppress(Exception):
                await self.storage.delete(key=storage_key)
            raise

    async def _read_limited(self, file: UploadFile) -> bytes:
        maximum = self.settings.KNOWLEDGE_MAX_FILE_SIZE_BYTES
        data = bytearray()
        while True:
            chunk = await file.read(min(_READ_CHUNK_SIZE, maximum + 1 - len(data)))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > maximum:
                raise KnowledgeFileTooLargeError()

    @staticmethod
    def _validate_signature(extension: str, data: bytes) -> None:
        if extension == ".pdf":
            if not data.startswith(b"%PDF-"):
                raise InvalidKnowledgeFileError()
            return
        if extension == ".docx":
            try:
                with ZipFile(BytesIO(data)) as archive:
                    if not _DOCX_REQUIRED_MEMBERS.issubset(archive.namelist()):
                        raise InvalidKnowledgeFileError()
            except BadZipFile:
                raise InvalidKnowledgeFileError() from None
            return
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise InvalidKnowledgeFileError() from None
        if "\x00" in text:
            raise InvalidKnowledgeFileError()
        controls = sum(
            1 for character in text if ord(character) < 32 and character not in "\n\r\t"
        )
        if controls > max(1, len(text) // 100):
            raise InvalidKnowledgeFileError()

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
