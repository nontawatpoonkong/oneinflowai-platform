"""Deterministic chunking, persistence, pipeline, and security tests."""

import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

import app.services.knowledge_document as knowledge_service_module
from app.chunking import RecursiveTextChunker
from app.core.config import Settings
from app.core.exceptions import KnowledgeChunkingFailedError
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_content import KnowledgeDocumentContent
from app.services.chunking import ChunkingService
from app.storage.local import LocalStorageProvider
from tests.conftest import (
    FakeEmailProvider,
    TestSessionLocal,
    register_verify_and_login,
)

BASE_URL = "/api/v1/knowledge"


def _chunker(size: int = 20, overlap: int = 5, maximum: int = 100):
    return RecursiveTextChunker(chunk_size=size, overlap=overlap, max_chunks=maximum)


def test_short_exact_boundary_and_empty_content() -> None:
    assert [chunk.text for chunk in _chunker().chunk("short")] == ["short"]
    exact = "x" * 20
    assert _chunker().chunk(exact)[0].text == exact
    with pytest.raises(ValueError, match="empty"):
        _chunker().chunk("")


def test_boundary_priority_and_hard_fallback() -> None:
    paragraph = _chunker(16, 0).chunk("aaaaa\n\nbbbbb ccccc")
    newline = _chunker(14, 0).chunk("aaaaaa\nbbb ccccc")
    sentence = _chunker(15, 0).chunk("First. Second long")
    whitespace = _chunker(12, 0).chunk("aaaaa bbbbb ccccc")
    hard = _chunker(8, 0).chunk("ก" * 20)
    assert paragraph[0].text.endswith("\n\n")
    assert newline[0].text.endswith("\n")
    assert sentence[0].text == "First. "
    assert whitespace[0].text.endswith(" ")
    assert hard[0].text == "ก" * 8


@pytest.mark.parametrize(
    "text",
    [
        "This is a long English document. " * 8,
        "ภาษาไทยไม่มีช่องว่างระหว่างคำ" * 8,
        "ไทย English 123 https://example.com 🙂 " * 8,
    ],
)
def test_language_overlap_offsets_order_and_determinism(text: str) -> None:
    first = _chunker(40, 8).chunk(text)
    second = _chunker(40, 8).chunk(text)
    assert first == second
    assert len(first) > 1
    assert all(chunk.text for chunk in first)
    assert all(len(chunk.text) <= 40 for chunk in first)
    assert all(text[c.start_offset : c.end_offset] == c.text for c in first)
    adjacent = zip(first, first[1:], strict=False)
    assert all(a.start_offset < b.start_offset for a, b in adjacent)
    adjacent = zip(first, first[1:], strict=False)
    assert all(a.end_offset > b.start_offset for a, b in adjacent)


def test_zero_overlap_forward_progress_and_maximum() -> None:
    chunks = _chunker(5, 0).chunk("x" * 13)
    assert [chunk.start_offset for chunk in chunks] == [0, 5, 10]
    with pytest.raises(ValueError, match="maximum"):
        _chunker(5, 1, 2).chunk("x" * 20)


def test_combining_and_emoji_boundaries_are_source_safe() -> None:
    text = "ภาษาไท\u0301ย🙂\u200d💻ทดสอบ" * 4
    chunks = _chunker(12, 3).chunk(text)
    assert "".join(text[c.start_offset : c.end_offset] for c in chunks)
    assert all(text[c.start_offset : c.end_offset] == c.text for c in chunks)
    assert all(not c.text.startswith(("\u0301", "\u200d")) for c in chunks)


def test_settings_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, KNOWLEDGE_CHUNK_SIZE=0)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            KNOWLEDGE_CHUNK_SIZE=10,
            KNOWLEDGE_CHUNK_OVERLAP=10,
        )
    assert (
        Settings(
            _env_file=None, KNOWLEDGE_CHUNK_SIZE=10, KNOWLEDGE_CHUNK_OVERLAP=0
        ).KNOWLEDGE_CHUNK_OVERLAP
        == 0
    )


@pytest.fixture
def chunk_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    return tmp_path


def _auth(client: TestClient, email: str) -> dict[str, str]:
    _, token = register_verify_and_login(client, email=email)
    return {"Authorization": f"Bearer {token}"}


def _upload(client: TestClient, headers: dict[str, str], text: str) -> dict:
    response = client.post(
        f"{BASE_URL}/upload",
        headers=headers,
        files={"file": ("chunks.txt", text.encode(), "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_pipeline_persists_hashes_and_chunk_api(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    chunk_storage: Path,
) -> None:
    headers = _auth(client_db, "chunks@example.com")
    text = "OneInFlow paragraph. " * 100
    document = _upload(client_db, headers, text)
    response = client_db.get(f"{BASE_URL}/{document['id']}/chunks", headers=headers)
    assert document["status"] == "READY"
    assert response.status_code == 200
    chunks = response.json()["data"]
    assert len(chunks) > 1
    assert [row["chunk_index"] for row in chunks] == list(range(len(chunks)))
    for row in chunks:
        assert row["content_hash"] == hashlib.sha256(row["text"].encode()).hexdigest()
        assert "storage_key" not in row and "path" not in row


def test_rechunk_is_idempotent_and_workspace_scoped(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    chunk_storage: Path,
) -> None:
    owner = _auth(client_db, "chunk-owner@example.com")
    document = _upload(client_db, owner, "repeatable text " * 120)
    before = client_db.get(f"{BASE_URL}/{document['id']}/chunks", headers=owner).json()[
        "data"
    ]
    result = client_db.post(f"{BASE_URL}/{document['id']}/rechunk", headers=owner)
    after = client_db.get(f"{BASE_URL}/{document['id']}/chunks", headers=owner).json()[
        "data"
    ]
    assert result.status_code == 200
    assert result.json()["data"]["chunk_count"] == len(after)
    assert [(x["text"], x["start_offset"]) for x in before] == [
        (x["text"], x["start_offset"]) for x in after
    ]
    other = _auth(client_db, "chunk-other@example.com")
    assert (
        client_db.get(f"{BASE_URL}/{document['id']}/chunks", headers=other).status_code
        == 404
    )
    assert (
        client_db.post(
            f"{BASE_URL}/{document['id']}/rechunk", headers=other
        ).status_code
        == 404
    )


def test_workspace_is_derived_unique_index_and_cascade(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    chunk_storage: Path,
) -> None:
    headers = _auth(client_db, "chunk-db@example.com")
    document = _upload(client_db, headers, "database content")

    async def verify() -> None:
        async with TestSessionLocal() as session:
            stored = await session.get(KnowledgeDocument, document["id"])
            rows = list((await session.execute(select(KnowledgeChunk))).scalars().all())
            assert stored is not None and rows[0].workspace_id == stored.workspace_id
            duplicate = KnowledgeChunk(
                document_id=rows[0].document_id,
                content_id=rows[0].content_id,
                workspace_id=rows[0].workspace_id,
                chunk_index=rows[0].chunk_index,
                text="duplicate",
                character_count=9,
                start_offset=0,
                end_offset=9,
                chunking_version="recursive-char-v1",
                content_hash="0" * 64,
            )
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
            await session.delete(stored)
            await session.commit()
            count = await session.scalar(select(func.count(KnowledgeChunk.id)))
            assert count == 0

    asyncio.run(verify())


def test_failed_replacement_rolls_back_previous_chunks(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    chunk_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client_db, "chunk-rollback@example.com")
    document = _upload(client_db, headers, "preserve this chunk set " * 80)

    async def verify() -> None:
        async with TestSessionLocal() as session:
            service = ChunkingService(session)
            before = await service.list_chunks(
                document["id"],
                (await session.get(KnowledgeDocument, document["id"])).workspace_id,
            )
            workspace_id = before[0].workspace_id
            expected = [(row.chunk_index, row.text) for row in before]

            async def broken_replace(content_id, rows):
                await service.chunks.session.execute(
                    KnowledgeChunk.__table__.delete().where(
                        KnowledgeChunk.content_id == content_id
                    )
                )
                raise RuntimeError("simulated persistence failure")

            monkeypatch.setattr(service.chunks, "replace", broken_replace)
            with pytest.raises(RuntimeError):
                await service.chunk_document(document["id"], workspace_id)
            preserved = await service.list_chunks(document["id"], workspace_id)
            assert [(x.chunk_index, x.text) for x in preserved] == expected

    asyncio.run(verify())


def test_automatic_chunking_failure_marks_failed_without_partial_chunks_or_leak(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    chunk_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_text = "private automatic chunk failure content"

    async def fail_chunking(self, document_id, workspace_id):
        raise KnowledgeChunkingFailedError()

    monkeypatch.setattr(ChunkingService, "chunk_document", fail_chunking)
    headers = _auth(client_db, "chunk-auto-failure@example.com")
    response = client_db.post(
        f"{BASE_URL}/upload",
        headers=headers,
        files={"file": ("failure.txt", secret_text.encode(), "text/plain")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "KNOWLEDGE_CHUNKING_FAILED"
    assert secret_text not in response.text
    assert "Traceback" not in response.text

    listing = client_db.get(BASE_URL, headers=headers).json()["data"]["items"]
    assert len(listing) == 1
    assert listing[0]["status"] == "FAILED"
    document_id = listing[0]["id"]
    content = client_db.get(
        f"{BASE_URL}/{document_id}/content", headers=headers
    ).json()["data"]
    chunks = client_db.get(f"{BASE_URL}/{document_id}/chunks", headers=headers).json()[
        "data"
    ]
    assert content["extracted_text"] == secret_text
    assert chunks == []


def test_retry_after_chunking_failure_rechunks_to_ready_without_duplicates(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    chunk_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_chunk_document = ChunkingService.chunk_document

    async def fail_chunking(self, document_id, workspace_id):
        raise KnowledgeChunkingFailedError()

    monkeypatch.setattr(ChunkingService, "chunk_document", fail_chunking)
    headers = _auth(client_db, "chunk-retry@example.com")
    failed = client_db.post(
        f"{BASE_URL}/upload",
        headers=headers,
        files={
            "file": (
                "retry.txt",
                ("retry chunking content " * 100).encode(),
                "text/plain",
            )
        },
    )
    assert failed.status_code == 422
    document = client_db.get(BASE_URL, headers=headers).json()["data"]["items"][0]
    assert document["status"] == "FAILED"

    monkeypatch.setattr(ChunkingService, "chunk_document", original_chunk_document)
    recovered = client_db.post(f"{BASE_URL}/{document['id']}/rechunk", headers=headers)
    assert recovered.status_code == 200
    detail = client_db.get(f"{BASE_URL}/{document['id']}", headers=headers).json()[
        "data"
    ]
    chunks = client_db.get(
        f"{BASE_URL}/{document['id']}/chunks", headers=headers
    ).json()["data"]
    assert detail["status"] == "READY"
    assert recovered.json()["data"]["chunk_count"] == len(chunks)
    assert [row["chunk_index"] for row in chunks] == list(range(len(chunks)))

    async def counts() -> tuple[int, int]:
        async with TestSessionLocal() as session:
            content_count = await session.scalar(
                select(func.count(KnowledgeDocumentContent.id)).where(
                    KnowledgeDocumentContent.document_id == document["id"]
                )
            )
            chunk_count = await session.scalar(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.document_id == document["id"]
                )
            )
            return int(content_count or 0), int(chunk_count or 0)

    assert asyncio.run(counts()) == (1, len(chunks))


def test_max_chunk_failure_pipeline_and_rechunk_preserve_valid_chunks(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    chunk_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limited = Settings(
        _env_file=None,
        KNOWLEDGE_CHUNK_SIZE=10,
        KNOWLEDGE_CHUNK_OVERLAP=0,
        KNOWLEDGE_MAX_CHUNKS_PER_DOCUMENT=1,
    )
    monkeypatch.setattr(knowledge_service_module, "get_settings", lambda: limited)
    headers = _auth(client_db, "chunk-limit@example.com")
    failed = client_db.post(
        f"{BASE_URL}/upload",
        headers=headers,
        files={"file": ("limited.txt", b"x" * 40, "text/plain")},
    )
    assert failed.status_code == 422
    failed_document = client_db.get(BASE_URL, headers=headers).json()["data"]["items"][
        0
    ]
    assert failed_document["status"] == "FAILED"
    assert (
        client_db.get(
            f"{BASE_URL}/{failed_document['id']}/chunks", headers=headers
        ).json()["data"]
        == []
    )

    normal = Settings(_env_file=None)
    monkeypatch.setattr(knowledge_service_module, "get_settings", lambda: normal)
    valid_document = _upload(client_db, headers, "valid existing chunks " * 100)

    async def verify_rechunk_rollback() -> None:
        async with TestSessionLocal() as session:
            document = await session.get(KnowledgeDocument, valid_document["id"])
            assert document is not None
            normal_service = ChunkingService(session, settings=normal)
            before = await normal_service.list_chunks(
                document.id, document.workspace_id
            )
            expected = [(row.chunk_index, row.text, row.content_hash) for row in before]
            limited_service = ChunkingService(session, settings=limited)
            with pytest.raises(
                KnowledgeChunkingFailedError, match="maximum chunk count"
            ):
                await limited_service.chunk_document(document.id, document.workspace_id)
            preserved = await normal_service.list_chunks(
                document.id, document.workspace_id
            )
            assert [
                (row.chunk_index, row.text, row.content_hash) for row in preserved
            ] == expected

    asyncio.run(verify_rechunk_rollback())


def test_content_hash_same_changed_and_rechunk_determinism(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    chunk_storage: Path,
) -> None:
    exact = "Exact persisted chunk text ไทย 🙂"
    changed = exact + " changed"
    same_hash_first = hashlib.sha256(exact.encode("utf-8")).hexdigest()
    same_hash_second = hashlib.sha256(exact.encode("utf-8")).hexdigest()
    changed_hash = hashlib.sha256(changed.encode("utf-8")).hexdigest()
    assert same_hash_first == same_hash_second
    assert same_hash_first != changed_hash
    assert same_hash_first == same_hash_first.lower()
    assert len(same_hash_first) == 64

    headers = _auth(client_db, "chunk-hash@example.com")
    document = _upload(client_db, headers, "hash determinism content " * 120)
    before = client_db.get(
        f"{BASE_URL}/{document['id']}/chunks", headers=headers
    ).json()["data"]
    assert all(
        row["content_hash"] == hashlib.sha256(row["text"].encode("utf-8")).hexdigest()
        for row in before
    )
    rechunked = client_db.post(f"{BASE_URL}/{document['id']}/rechunk", headers=headers)
    assert rechunked.status_code == 200
    after = client_db.get(
        f"{BASE_URL}/{document['id']}/chunks", headers=headers
    ).json()["data"]
    assert [row["content_hash"] for row in after] == [
        row["content_hash"] for row in before
    ]
