"""File-signature and storage-failure hardening tests."""

import asyncio
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

import app.services.knowledge_document as knowledge_service_module
from app.core.config import Settings
from app.core.exceptions import KnowledgeFileTooLargeError
from app.services.knowledge_document import KnowledgeDocumentService
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider
from tests.conftest import FakeEmailProvider, register_verify_and_login

BASE_URL = "/api/v1/knowledge"


def _auth(client: TestClient, provider: FakeEmailProvider) -> dict[str, str]:
    _, token = register_verify_and_login(client, email="hardening@example.com")
    return {"Authorization": f"Bearer {token}"}


def _upload(
    client: TestClient,
    headers: dict[str, str],
    filename: str,
    content: bytes,
    content_type: str,
):
    return client.post(
        f"{BASE_URL}/upload",
        headers=headers,
        files={"file": (filename, content, content_type)},
    )


def _docx(*, valid: bool) -> bytes:
    if valid:
        output = BytesIO()
        document = Document()
        document.add_paragraph("Valid document")
        document.save(output)
        return output.getvalue()
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        if valid:
            archive.writestr("word/document.xml", "<document />")
        else:
            archive.writestr("random.txt", "not a document")
    return output.getvalue()


def _pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Valid PDF) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("valid.pdf", _pdf(), "application/pdf"),
        (
            "valid.docx",
            _docx(valid=True),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("valid.txt", "สวัสดี OneFlowAI".encode(), "text/plain"),
        ("valid.md", b"# Knowledge\n\nContent", "text/markdown"),
        ("bom.txt", b"\xef\xbb\xbfUTF-8 content", "text/plain"),
    ],
    ids=["pdf", "docx", "txt", "markdown", "utf8-bom"],
)
def test_valid_signatures_are_accepted(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content: bytes,
    content_type: str,
) -> None:
    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    response = _upload(
        client_db,
        _auth(client_db, fake_email_provider),
        filename,
        content,
        content_type,
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("fake.pdf", b"MZ executable", "application/pdf"),
        (
            "fake.docx",
            _docx(valid=False),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("binary.txt", b"hello\x00world\x01", "text/plain"),
    ],
    ids=["fake-pdf", "fake-docx", "binary-txt"],
)
def test_mismatched_or_binary_files_are_rejected(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content: bytes,
    content_type: str,
) -> None:
    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    response = _upload(
        client_db,
        _auth(client_db, fake_email_provider),
        filename,
        content,
        content_type,
    )
    assert response.status_code == 400
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_path_traversal_cannot_escape_storage_root(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    provider = LocalStorageProvider(root)
    with pytest.raises(ValueError, match="Invalid storage key"):
        asyncio.run(provider.save(key="../escape.txt", data=b"unsafe"))
    assert not (tmp_path / "escape.txt").exists()


def test_oversize_read_is_bounded() -> None:
    class RecordingUpload(UploadFile):
        read_sizes: list[int]

        def __init__(self) -> None:
            super().__init__(BytesIO(b"12345"), filename="guide.txt")
            self.read_sizes = []

        async def read(self, size: int = -1) -> bytes:
            self.read_sizes.append(size)
            return await super().read(size)

    upload = RecordingUpload()
    settings = Settings(_env_file=None, KNOWLEDGE_MAX_FILE_SIZE_BYTES=4)
    service = KnowledgeDocumentService(
        object(), storage=LocalStorageProvider("."), settings=settings
    )
    with pytest.raises(KnowledgeFileTooLargeError):
        asyncio.run(service._read_limited(upload))
    assert upload.read_sizes == [5]


def test_storage_failure_leaves_no_successful_metadata(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client_db, fake_email_provider)

    class FailingStorage(StorageProvider):
        async def save(self, *, key: str, data: bytes) -> None:
            raise OSError("storage unavailable")

        async def read(self, *, key: str) -> bytes:
            raise OSError("storage unavailable")

        async def delete(self, *, key: str) -> None:
            return None

    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: FailingStorage(),
    )
    with pytest.raises(OSError, match="storage unavailable"):
        _upload(client_db, headers, "guide.txt", b"content", "text/plain")
    listing = client_db.get(BASE_URL, headers=headers)
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] == 0


def test_database_failure_removes_written_file(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client_db, fake_email_provider)
    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )

    async def _fail_commit(self) -> None:
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(AsyncSession, "commit", _fail_commit)
    with pytest.raises(RuntimeError, match="database commit failed"):
        _upload(client_db, headers, "guide.txt", b"content", "text/plain")
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_deleting_already_missing_file_is_idempotent(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    headers = _auth(client_db, fake_email_provider)
    uploaded = _upload(
        client_db, headers, "guide.txt", b"content", "text/plain"
    ).json()["data"]
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.unlink()
    response = client_db.delete(f"{BASE_URL}/{uploaded['id']}", headers=headers)
    assert response.status_code == 200
