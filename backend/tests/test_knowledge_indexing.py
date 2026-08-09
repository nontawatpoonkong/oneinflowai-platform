"""PostgreSQL-backed knowledge indexing lifecycle and synchronization tests."""

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.knowledge.router as knowledge_router_module
import app.services.knowledge_document as knowledge_service_module
from app.core.config import Settings
from app.core.exceptions import (
    EmbeddingProviderError,
    KnowledgeDocumentNotFoundError,
    KnowledgeIndexingError,
    VectorCollectionConfigurationError,
)
from app.integrations.embedding import DevelopmentEmbeddingProvider
from app.integrations.qdrant_knowledge import QdrantKnowledgeVectorStore
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument, KnowledgeIndexStatus
from app.services.knowledge_indexing import KnowledgeIndexingService
from app.storage.local import LocalStorageProvider
from tests.conftest import (
    FakeEmailProvider,
    TestSessionLocal,
    register_verify_and_login,
)

BASE_URL = "/api/v1/knowledge"


class FakeVectorStore:
    def __init__(self) -> None:
        self.dimensions: int | None = None
        self.points: dict[uuid.UUID, object] = {}
        self.fail_upsert = False
        self.ensure_calls = 0

    async def ensure_collection(self, dimensions: int) -> None:
        self.ensure_calls += 1
        if self.dimensions is not None and self.dimensions != dimensions:
            raise RuntimeError("incompatible dimensions")
        self.dimensions = dimensions

    async def current_point_ids(self, workspace_id, document_id):
        return {
            point_id
            for point_id, point in self.points.items()
            if point.payload["workspace_id"] == str(workspace_id)
            and point.payload["document_id"] == str(document_id)
        }

    async def upsert(self, points):
        if self.fail_upsert:
            raise RuntimeError("qdrant unavailable")
        self.points.update({uuid.UUID(str(point.id)): point for point in points})

    async def delete_ids(self, point_ids):
        for point_id in point_ids:
            self.points.pop(point_id, None)


class FailingEmbeddingProvider(DevelopmentEmbeddingProvider):
    async def embed_texts(self, texts):
        raise EmbeddingProviderError()


class FakeQdrantClient:
    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions
        self.create_calls = 0
        self.payload_indexes: list[str] = []

    async def collection_exists(self, collection_name):
        return self.dimensions is not None

    async def create_collection(self, collection_name, vectors_config):
        self.create_calls += 1
        self.dimensions = vectors_config.size

    async def get_collection(self, collection_name):
        vectors = SimpleNamespace(size=self.dimensions)
        return SimpleNamespace(
            config=SimpleNamespace(params=SimpleNamespace(vectors=vectors))
        )

    async def create_payload_index(self, collection_name, field_name, **kwargs):
        self.payload_indexes.append(field_name)


@pytest.fixture
def indexing_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
        files={"file": ("index.txt", text.encode(), "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["data"]


async def test_collection_creation_is_idempotent_and_dimension_safe() -> None:
    client = FakeQdrantClient()
    store = QdrantKnowledgeVectorStore(client, collection_name="knowledge_chunks")
    await store.ensure_collection(8)
    await store.ensure_collection(8)
    assert client.create_calls == 1
    assert client.payload_indexes == [
        "workspace_id",
        "document_id",
        "chunk_id",
        "workspace_id",
        "document_id",
        "chunk_id",
    ]
    incompatible = QdrantKnowledgeVectorStore(
        FakeQdrantClient(dimensions=16), collection_name="knowledge_chunks"
    )
    with pytest.raises(VectorCollectionConfigurationError):
        await incompatible.ensure_collection(8)


async def _index(document_id: str, store, provider=None, settings=None):
    async with TestSessionLocal() as session:
        document = await session.get(KnowledgeDocument, document_id)
        assert document is not None
        service = KnowledgeIndexingService(
            session,
            vector_store=store,
            provider=provider or DevelopmentEmbeddingProvider(),
            settings=settings
            or Settings(_env_file=None, EMBEDDING_PROVIDER="development"),
        )
        return await service.index_document(document.id, document.workspace_id)


def test_upload_is_ready_with_pending_index(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    indexing_storage: Path,
) -> None:
    document = _upload(client_db, _auth(client_db, "pending@example.com"), "ready")
    assert document["status"] == "READY"
    assert document["index_status"] == "PENDING"
    assert document["indexed_at"] is None


def test_explicit_index_endpoint_makes_document_indexed(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    indexing_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, EMBEDDING_PROVIDER="development")
    store = FakeVectorStore()
    monkeypatch.setattr(knowledge_router_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        knowledge_router_module,
        "create_embedding_provider",
        lambda configured: DevelopmentEmbeddingProvider(),
    )
    monkeypatch.setattr(
        knowledge_router_module,
        "QdrantKnowledgeVectorStore",
        lambda client, collection_name: store,
    )
    headers = _auth(client_db, "index-endpoint@example.com")
    document = _upload(client_db, headers, "explicit endpoint content " * 80)
    response = client_db.post(f"{BASE_URL}/{document['id']}/index", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["document_id"] == document["id"]
    assert data["index_status"] == "INDEXED"
    assert data["chunk_count"] == len(store.points) > 0
    assert data["embedding_model"] == "development-sha256"
    assert data["indexed_at"] is not None


def test_index_success_payload_metadata_batching_and_idempotency(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    indexing_storage: Path,
) -> None:
    headers = _auth(client_db, "indexed@example.com")
    document = _upload(client_db, headers, "indexed content " * 200)
    store = FakeVectorStore()
    settings = Settings(
        _env_file=None, EMBEDDING_PROVIDER="development", EMBEDDING_BATCH_SIZE=1
    )
    first = asyncio.run(_index(document["id"], store, settings=settings))
    first_ids = set(store.points)
    second = asyncio.run(_index(document["id"], store, settings=settings))
    assert first.chunk_count == second.chunk_count == len(store.points)
    assert first.embedding_request_count == first.chunk_count
    assert set(store.points) == first_ids
    assert store.ensure_calls == 2
    for point_id, point in store.points.items():
        payload = point.payload
        assert point_id == uuid.UUID(payload["chunk_id"])
        assert payload["workspace_id"] == document["workspace_id"]
        assert payload["document_id"] == document["id"]
        assert "text" not in payload and "vector" not in payload
        assert payload["embedding_version"] == "development:sha256:8:v1"

    async def verify_metadata() -> None:
        async with TestSessionLocal() as session:
            stored = await session.get(KnowledgeDocument, document["id"])
            chunks = list(
                (
                    await session.execute(
                        select(KnowledgeChunk).where(
                            KnowledgeChunk.document_id == document["id"]
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert stored is not None
            assert stored.index_status is KnowledgeIndexStatus.INDEXED
            assert stored.indexed_at is not None
            assert all(
                chunk.embedding_model == "development-sha256" for chunk in chunks
            )
            assert all(chunk.indexed_at is not None for chunk in chunks)

    asyncio.run(verify_metadata())


def test_rechunk_resets_pending_and_reindex_removes_stale_points(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    indexing_storage: Path,
) -> None:
    headers = _auth(client_db, "stale@example.com")
    document = _upload(client_db, headers, "stale vectors " * 200)
    store = FakeVectorStore()
    asyncio.run(_index(document["id"], store))
    old_ids = set(store.points)
    response = client_db.post(f"{BASE_URL}/{document['id']}/rechunk", headers=headers)
    assert response.status_code == 200
    detail = client_db.get(f"{BASE_URL}/{document['id']}", headers=headers).json()[
        "data"
    ]
    assert detail["index_status"] == "PENDING"
    assert detail["indexed_at"] is None
    asyncio.run(_index(document["id"], store))
    assert old_ids.isdisjoint(set(store.points))
    assert len(store.points) > 0


@pytest.mark.parametrize("failure", ["embedding", "qdrant"])
def test_index_failure_marks_failed_preserves_chunks_and_previous_vectors(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    indexing_storage: Path,
    failure: str,
) -> None:
    headers = _auth(client_db, f"{failure}@example.com")
    document = _upload(client_db, headers, "failure-safe content " * 100)
    store = FakeVectorStore()
    asyncio.run(_index(document["id"], store))
    previous_ids = set(store.points)
    provider = FailingEmbeddingProvider()
    if failure == "qdrant":
        provider = DevelopmentEmbeddingProvider()
        store.fail_upsert = True
    expected_error = (
        EmbeddingProviderError if failure == "embedding" else KnowledgeIndexingError
    )
    with pytest.raises(expected_error):
        asyncio.run(_index(document["id"], store, provider=provider))
    assert set(store.points) == previous_ids

    async def verify() -> None:
        async with TestSessionLocal() as session:
            stored = await session.get(KnowledgeDocument, document["id"])
            count = await session.scalar(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.document_id == document["id"]
                )
            )
            assert stored is not None
            assert stored.index_status is KnowledgeIndexStatus.FAILED
            assert stored.index_error_code is not None
            assert int(count or 0) > 0

    asyncio.run(verify())


def test_cross_workspace_indexing_is_rejected(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    indexing_storage: Path,
) -> None:
    owner = _auth(client_db, "index-owner@example.com")
    document = _upload(client_db, owner, "private index")
    _auth(client_db, "index-other@example.com")

    async def verify() -> None:
        async with TestSessionLocal() as session:
            stored = await session.get(KnowledgeDocument, document["id"])
            assert stored is not None
            service = KnowledgeIndexingService(
                session,
                vector_store=FakeVectorStore(),
                provider=DevelopmentEmbeddingProvider(),
                settings=Settings(_env_file=None, EMBEDDING_PROVIDER="development"),
            )
            with pytest.raises(KnowledgeDocumentNotFoundError):
                await service.index_document(stored.id, uuid.uuid4())

    asyncio.run(verify())
