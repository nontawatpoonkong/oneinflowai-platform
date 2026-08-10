"""Workspace-safe semantic retrieval tests with no external network calls."""

import asyncio
import logging
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.knowledge.router as knowledge_router_module
import app.services.knowledge_document as knowledge_service_module
from app.core.config import Settings
from app.core.exceptions import (
    EmbeddingProviderError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentNotIndexedError,
    KnowledgeRetrievalError,
    KnowledgeRetrievalValidationError,
    VectorCollectionConfigurationError,
)
from app.integrations.embedding import DevelopmentEmbeddingProvider
from app.integrations.qdrant_knowledge import VectorSearchHit
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeIndexStatus,
)
from app.services.knowledge_retrieval import KnowledgeRetrievalService
from app.storage.local import LocalStorageProvider
from tests.conftest import (
    FakeEmailProvider,
    TestSessionLocal,
    register_verify_and_login,
)

BASE_URL = "/api/v1/knowledge"


class FakeSearchStore:
    def __init__(self, hits: list[VectorSearchHit] | None = None) -> None:
        self.hits = hits or []
        self.search_calls: list[dict] = []
        self.validated_dimensions: list[int] = []
        self.failure: Exception | None = None

    async def validate_collection(self, dimensions: int) -> None:
        self.validated_dimensions.append(dimensions)
        if self.failure:
            raise self.failure

    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        if self.failure:
            raise self.failure
        return self.hits


class RecordingProvider(DevelopmentEmbeddingProvider):
    def __init__(self, *, dimensions: int = 8, fail: bool = False) -> None:
        super().__init__(dimensions=dimensions)
        self.calls: list[list[str]] = []
        self.fail = fail

    async def embed_texts(self, texts):
        self.calls.append(texts)
        if self.fail:
            raise EmbeddingProviderError()
        return await super().embed_texts(texts)


@pytest.fixture
def retrieval_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
        files={"file": ("retrieval.txt", text.encode(), "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["data"]


def _mark_indexed(document_id: str) -> tuple[uuid.UUID, list[KnowledgeChunk]]:
    async def update() -> tuple[uuid.UUID, list[KnowledgeChunk]]:
        async with TestSessionLocal() as session:
            document = await session.get(KnowledgeDocument, document_id)
            assert document is not None
            document.index_status = KnowledgeIndexStatus.INDEXED
            chunks = list(
                (
                    await session.execute(
                        select(KnowledgeChunk)
                        .where(KnowledgeChunk.document_id == document.id)
                        .order_by(KnowledgeChunk.chunk_index)
                    )
                )
                .scalars()
                .all()
            )
            for chunk in chunks:
                chunk.embedding_model = "development-sha256"
                chunk.embedding_version = "development:sha256:8:v1"
            await session.commit()
            for chunk in chunks:
                session.expunge(chunk)
            return document.workspace_id, chunks

    return asyncio.run(update())


def _hit(
    chunk: KnowledgeChunk,
    workspace_id: uuid.UUID,
    score: float,
    **payload_overrides,
) -> VectorSearchHit:
    payload = {
        "workspace_id": str(workspace_id),
        "document_id": str(chunk.document_id),
        "chunk_id": str(chunk.id),
        "embedding_model": "development-sha256",
        "embedding_version": "development:sha256:8:v1",
        "text": "untrusted qdrant text",
    }
    payload.update(payload_overrides)
    return VectorSearchHit(point_id=chunk.id, score=score, payload=payload)


async def _search(workspace_id, store, **kwargs):
    async with TestSessionLocal() as session:
        service = KnowledgeRetrievalService(
            session,
            vector_store=store,
            provider=kwargs.pop("provider", RecordingProvider()),
            settings=kwargs.pop(
                "settings", Settings(_env_file=None, EMBEDDING_PROVIDER="development")
            ),
        )
        return await service.search(workspace_id=workspace_id, **kwargs)


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_queries_are_rejected(query: str) -> None:
    with pytest.raises(KnowledgeRetrievalValidationError):
        asyncio.run(_search(uuid.uuid4(), FakeSearchStore(), query=query))


def test_query_length_limit_and_result_limit_validation() -> None:
    settings = Settings(
        _env_file=None,
        EMBEDDING_PROVIDER="development",
        KNOWLEDGE_RETRIEVAL_MAX_QUERY_CHARACTERS=5,
        KNOWLEDGE_RETRIEVAL_MAX_LIMIT=3,
        KNOWLEDGE_RETRIEVAL_DEFAULT_LIMIT=2,
    )
    with pytest.raises(KnowledgeRetrievalValidationError, match="too long"):
        asyncio.run(
            _search(uuid.uuid4(), FakeSearchStore(), query="123456", settings=settings)
        )
    with pytest.raises(KnowledgeRetrievalValidationError, match="limit"):
        asyncio.run(
            _search(
                uuid.uuid4(),
                FakeSearchStore(),
                query="valid",
                limit=4,
                settings=settings,
            )
        )


@pytest.mark.parametrize("query", ["ร้านเปิดกี่โมง", "ร้านเปิดกี่โมง OneInFlow?"])
def test_query_is_trimmed_and_unicode_preserved(query: str) -> None:
    provider = RecordingProvider()
    store = FakeSearchStore()
    result = asyncio.run(
        _search(uuid.uuid4(), store, query=f"  {query}  ", provider=provider)
    )
    assert result.query == query
    assert provider.calls == [[query]]
    assert len(store.search_calls) == 1


def test_default_limit_threshold_model_and_workspace_are_passed() -> None:
    workspace_id = uuid.uuid4()
    settings = Settings(
        _env_file=None,
        EMBEDDING_PROVIDER="development",
        KNOWLEDGE_RETRIEVAL_DEFAULT_LIMIT=7,
        KNOWLEDGE_RETRIEVAL_SCORE_THRESHOLD=0.25,
    )
    store = FakeSearchStore()
    asyncio.run(_search(workspace_id, store, query="query", settings=settings))
    call = store.search_calls[0]
    assert call["workspace_id"] == workspace_id
    assert call["limit"] == 7
    assert call["score_threshold"] == 0.25
    assert call["embedding_model"] == "development-sha256"
    assert call["embedding_version"] == "development:sha256:8:v1"


def test_results_use_postgres_text_preserve_rank_and_skip_stale(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    retrieval_storage: Path,
) -> None:
    headers = _auth(client_db, "retrieval-results@example.com")
    document = _upload(client_db, headers, "first paragraph. " * 200)
    workspace_id, chunks = _mark_indexed(document["id"])
    assert len(chunks) >= 2
    missing_id = uuid.uuid4()
    store = FakeSearchStore(
        [
            _hit(chunks[1], workspace_id, 0.91),
            VectorSearchHit(missing_id, 0.90, {}),
            _hit(chunks[0], workspace_id, 0.73),
        ]
    )
    result = asyncio.run(_search(workspace_id, store, query="paragraph"))
    assert [item.chunk_id for item in result.results] == [chunks[1].id, chunks[0].id]
    assert [item.score for item in result.results] == [0.91, 0.73]
    assert result.results[0].text == chunks[1].text
    assert result.results[0].text != "untrusted qdrant text"


def test_cross_workspace_and_incompatible_payload_results_are_discarded(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    retrieval_storage: Path,
) -> None:
    first = _auth(client_db, "retrieval-first@example.com")
    first_doc = _upload(client_db, first, "trusted workspace")
    first_workspace, first_chunks = _mark_indexed(first_doc["id"])
    second = _auth(client_db, "retrieval-second@example.com")
    second_doc = _upload(client_db, second, "foreign workspace")
    second_workspace, second_chunks = _mark_indexed(second_doc["id"])
    store = FakeSearchStore(
        [
            _hit(second_chunks[0], second_workspace, 0.99),
            _hit(first_chunks[0], first_workspace, 0.88, embedding_model="stale"),
        ]
    )
    result = asyncio.run(_search(first_workspace, store, query="workspace"))
    assert result.results == []


@pytest.mark.parametrize(
    ("status", "index_status"),
    [
        (KnowledgeDocumentStatus.DELETED, KnowledgeIndexStatus.INDEXED),
        (KnowledgeDocumentStatus.FAILED, KnowledgeIndexStatus.INDEXED),
        (KnowledgeDocumentStatus.READY, KnowledgeIndexStatus.PENDING),
        (KnowledgeDocumentStatus.READY, KnowledgeIndexStatus.FAILED),
    ],
)
def test_invalid_document_state_results_are_skipped(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    retrieval_storage: Path,
    status: KnowledgeDocumentStatus,
    index_status: KnowledgeIndexStatus,
) -> None:
    headers = _auth(client_db, f"retrieval-{status}-{index_status}@example.com")
    document = _upload(client_db, headers, "state filtered")
    workspace_id, chunks = _mark_indexed(document["id"])

    async def mutate() -> None:
        async with TestSessionLocal() as session:
            stored = await session.get(KnowledgeDocument, document["id"])
            assert stored is not None
            stored.status = status
            stored.index_status = index_status
            await session.commit()

    asyncio.run(mutate())
    result = asyncio.run(
        _search(
            workspace_id,
            FakeSearchStore([_hit(chunks[0], workspace_id, 0.8)]),
            query="state",
        )
    )
    assert result.results == []


def test_document_scope_is_trusted_and_requires_indexed_document(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    retrieval_storage: Path,
) -> None:
    owner = _auth(client_db, "scope-owner@example.com")
    document = _upload(client_db, owner, "document scope")
    workspace_id, _ = _mark_indexed(document["id"])
    store = FakeSearchStore()
    asyncio.run(
        _search(
            workspace_id,
            store,
            query="scope",
            document_id=uuid.UUID(document["id"]),
        )
    )
    assert store.search_calls[0]["document_id"] == uuid.UUID(document["id"])
    with pytest.raises(KnowledgeDocumentNotFoundError):
        asyncio.run(
            _search(
                uuid.uuid4(),
                FakeSearchStore(),
                query="scope",
                document_id=uuid.UUID(document["id"]),
            )
        )

    pending = _upload(client_db, owner, "pending scope")
    with pytest.raises(KnowledgeDocumentNotIndexedError):
        asyncio.run(
            _search(
                workspace_id,
                FakeSearchStore(),
                query="scope",
                document_id=uuid.UUID(pending["id"]),
            )
        )


@pytest.mark.parametrize(
    ("provider", "store", "expected"),
    [
        (RecordingProvider(fail=True), FakeSearchStore(), EmbeddingProviderError),
        (
            RecordingProvider(),
            FakeSearchStore(),
            VectorCollectionConfigurationError,
        ),
    ],
)
def test_embedding_and_collection_failures_are_typed(provider, store, expected) -> None:
    if expected is VectorCollectionConfigurationError:
        store.failure = VectorCollectionConfigurationError()
    with pytest.raises(expected):
        asyncio.run(_search(uuid.uuid4(), store, query="failure", provider=provider))


def test_qdrant_runtime_failure_is_mapped_safely() -> None:
    store = FakeSearchStore()
    store.failure = RuntimeError("connection secret")
    with pytest.raises(KnowledgeRetrievalError) as captured:
        asyncio.run(_search(uuid.uuid4(), store, query="safe query"))
    assert "connection secret" not in str(captured.value)


def test_search_endpoint_returns_empty_without_workspace_injection(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    retrieval_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, EMBEDDING_PROVIDER="development")
    store = FakeSearchStore()
    monkeypatch.setattr(knowledge_router_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        knowledge_router_module,
        "create_embedding_provider",
        lambda configured: RecordingProvider(),
    )
    monkeypatch.setattr(
        knowledge_router_module,
        "QdrantKnowledgeVectorStore",
        lambda client, collection_name: store,
    )
    headers = _auth(client_db, "retrieval-api@example.com")
    response = client_db.post(
        f"{BASE_URL}/search",
        headers=headers,
        json={"query": "  ร้านเปิดกี่โมง  ", "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"query": "ร้านเปิดกี่โมง", "results": []}
    injected = client_db.post(
        f"{BASE_URL}/search",
        headers=headers,
        json={"query": "test", "workspace_id": str(uuid.uuid4())},
    )
    assert injected.status_code == 200
    assert (
        store.search_calls[-1]["workspace_id"] == store.search_calls[-2]["workspace_id"]
    )


def test_logs_do_not_contain_query_or_chunk_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_query = "private-query-content"
    with caplog.at_level(logging.INFO):
        asyncio.run(_search(uuid.uuid4(), FakeSearchStore(), query=secret_query))
    assert secret_query not in caplog.text
