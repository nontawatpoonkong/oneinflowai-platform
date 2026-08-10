"""Direct orchestration and authenticated RAG preview API tests."""

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services.knowledge_retrieval import RetrievalResponse
from app.services.rag_preparation import RAGPreparationService
from tests.conftest import register_verify_and_login
from tests.test_rag_context import _result


class FakeRetrieval:
    def __init__(self, results=None, failure=None):
        self.results = results or []
        self.failure = failure
        self.calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return RetrievalResponse(query=kwargs["query"].strip(), results=self.results)


def test_preparation_chains_retrieval_context_and_prompt_without_generation() -> None:
    retrieval = FakeRetrieval([_result("answer", 1)])
    service = RAGPreparationService(retrieval, settings=Settings(_env_file=None))
    workspace_id, document_id = uuid.uuid4(), uuid.uuid4()
    package = asyncio.run(
        service.prepare(
            workspace_id=workspace_id, query=" q ", limit=3, document_id=document_id
        )
    )
    assert retrieval.calls == [
        {
            "workspace_id": workspace_id,
            "query": " q ",
            "limit": 3,
            "document_id": document_id,
        }
    ]
    assert package.context.query == "q"
    assert package.sources[0].text == "answer"


def test_preparation_propagates_retrieval_failure() -> None:
    service = RAGPreparationService(
        FakeRetrieval(failure=RuntimeError("failed")), settings=Settings(_env_file=None)
    )
    try:
        asyncio.run(service.prepare(workspace_id=uuid.uuid4(), query="q"))
    except RuntimeError as exc:
        assert str(exc) == "failed"
    else:
        raise AssertionError("retrieval failure was swallowed")


def test_rag_preview_requires_authentication(client_db: TestClient) -> None:
    response = client_db.post("/api/v1/knowledge/rag-preview", json={"query": "q"})
    assert response.status_code == 401


def test_rag_preview_returns_safe_no_result_package(
    client_db: TestClient, monkeypatch
) -> None:
    import app.knowledge.router as router_module

    settings = Settings(_env_file=None, EMBEDDING_PROVIDER="development")
    monkeypatch.setattr(router_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        router_module, "create_embedding_provider", lambda configured: object()
    )
    monkeypatch.setattr(
        router_module, "QdrantKnowledgeVectorStore", lambda *args, **kwargs: object()
    )
    captured = {}

    async def fake_search(self, **kwargs):
        captured.update(kwargs)
        return RetrievalResponse(query=kwargs["query"].strip(), results=[])

    monkeypatch.setattr(router_module.KnowledgeRetrievalService, "search", fake_search)
    _, token = register_verify_and_login(client_db, email="rag-preview@example.com")
    injected_workspace_id = uuid.uuid4()
    response = client_db.post(
        "/api/v1/knowledge/rag-preview",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "  ไม่มีข้อมูล  ", "workspace_id": str(injected_workspace_id)},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"] == "ไม่มีข้อมูล"
    assert data["sources"] == []
    assert data["included_chunk_count"] == data["omitted_chunk_count"] == 0
    assert "No relevant knowledge sources" in data["user_prompt"]
    assert "system_prompt" not in data
    assert "vector" not in str(data).lower()
    assert "storage_path" not in str(data)
    assert captured["workspace_id"] != injected_workspace_id
