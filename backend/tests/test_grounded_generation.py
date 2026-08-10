"""Grounding, citations, language, orchestration, and answer API tests."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import GroundingValidationError
from app.integrations.generation import GenerationResult
from app.rag.context import RAGContextAssembler
from app.rag.prompt import RAGPromptBuilder
from app.services.grounded_generation import (
    GroundedGenerationService,
    GroundingStatus,
    validate_citations,
)
from tests.conftest import register_verify_and_login
from tests.test_rag_context import _result


def _package(query="question", count=2):
    results = [_result(f"source {index}", 1 - index / 10) for index in range(count)]
    context = RAGContextAssembler(max_characters=10_000, max_sources=8).assemble(
        query, results
    )
    return RAGPromptBuilder().build(query=query, context=context)


class FakePreparation:
    def __init__(self, package):
        self.package = package
        self.calls = []

    async def prepare(self, **kwargs):
        self.calls.append(kwargs)
        return self.package


class FakeProvider:
    name = "fake"

    def __init__(self, text="answer [S1]", failure=None, usage=True):
        self.text, self.failure, self.usage = text, failure, usage
        self.calls = []

    async def generate(self, prompt):
        self.calls.append(prompt)
        if self.failure:
            raise self.failure
        return GenerationResult(
            text=self.text,
            model="test-model",
            provider="fake",
            input_tokens=10 if self.usage else None,
            output_tokens=3 if self.usage else None,
            total_tokens=13 if self.usage else None,
        )


def _service(package, provider):
    return GroundedGenerationService(
        FakePreparation(package),
        provider,
        settings=Settings(_env_file=None, GENERATION_PROVIDER="development"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("ร้านเปิดกี่โมง", "ไม่พบข้อมูลเพียงพอ"),
        ("When are you open?", "There is not enough information"),
    ],
)
async def test_zero_sources_skips_provider_with_language_fallback(
    query, expected
) -> None:
    package, provider = _package(query, 0), FakeProvider()
    answer = await _service(package, provider).answer(
        workspace_id=uuid.uuid4(), query=query
    )
    assert expected in answer.answer
    assert answer.grounding_status is GroundingStatus.NO_KNOWLEDGE
    assert answer.generation_skipped and provider.calls == []
    assert answer.citations == [] and answer.usage is None
    assert answer.model is answer.provider is None


@pytest.mark.asyncio
async def test_zero_sources_does_not_require_external_provider_configuration() -> None:
    package = _package("unknown", 0)
    service = GroundedGenerationService(
        FakePreparation(package), settings=Settings(_env_file=None, OPENAI_API_KEY=None)
    )
    answer = await service.answer(workspace_id=uuid.uuid4(), query="unknown")
    assert answer.generation_skipped


def test_citations_validate_deduplicate_and_preserve_first_use_order() -> None:
    sources = _package().sources
    citations = validate_citations("second [S2], first [S1], second [S2]", sources)
    assert [citation.label for citation in citations] == ["S2", "S1"]
    assert citations[0].chunk_id == sources[1].chunk_id


@pytest.mark.parametrize("answer", ["invented [S9]", "valid [S1] invalid [S9]"])
def test_unknown_citations_are_rejected(answer) -> None:
    with pytest.raises(GroundingValidationError) as captured:
        validate_citations(answer, _package().sources)
    assert captured.value.details == {
        "grounding_status": GroundingStatus.INVALID_CITATIONS
    }


@pytest.mark.parametrize("answer", ["no citations", "malformed [S0] and S1 and [s1]"])
def test_missing_or_malformed_citations_are_rejected(answer) -> None:
    with pytest.raises(GroundingValidationError) as captured:
        validate_citations(answer, _package().sources)
    assert captured.value.details == {
        "grounding_status": GroundingStatus.MISSING_CITATIONS
    }


@pytest.mark.asyncio
async def test_generation_uses_exact_prepared_prompts_and_server_controls() -> None:
    package, provider = _package("ไทย English"), FakeProvider("kept exactly [S1]")
    service = _service(package, provider)
    answer = await service.answer(
        workspace_id=uuid.uuid4(),
        query="ไทย English",
        limit=4,
        document_id=uuid.uuid4(),
    )
    request = provider.calls[0]
    assert request.system_prompt == package.system_prompt
    assert request.user_prompt == package.user_prompt
    assert (request.temperature, request.max_output_tokens) == (0.2, 800)
    assert answer.answer == "kept exactly [S1]"
    assert answer.grounding_status is GroundingStatus.VERIFIED
    assert answer.usage.total_tokens == 13
    assert answer.prompt_version == package.version
    assert answer.context_version == package.context.version


@pytest.mark.asyncio
async def test_missing_usage_is_safe_and_provider_failure_propagates() -> None:
    package = _package()
    answer = await _service(package, FakeProvider(usage=False)).answer(
        workspace_id=uuid.uuid4(), query="question"
    )
    assert answer.usage is None
    failure = RuntimeError("private source prompt")
    with pytest.raises(RuntimeError):
        await _service(package, FakeProvider(failure=failure)).answer(
            workspace_id=uuid.uuid4(), query="secret query"
        )


def test_answer_endpoint_requires_authentication(client_db: TestClient) -> None:
    assert (
        client_db.post("/api/v1/knowledge/answer", json={"query": "q"}).status_code
        == 401
    )


def test_answer_endpoint_uses_auth_workspace_and_rejects_client_controls(
    client_db: TestClient, monkeypatch
) -> None:
    import app.knowledge.router as router_module

    package = _package("ถาม")
    captured = {}
    original_answer = GroundedGenerationService.answer

    async def fake_answer(self, **kwargs):
        captured.update(kwargs)
        provider = FakeProvider()
        return await original_answer(_service(package, provider), **kwargs)

    monkeypatch.setattr(router_module.GroundedGenerationService, "answer", fake_answer)
    monkeypatch.setattr(
        router_module, "create_embedding_provider", lambda settings: object()
    )
    monkeypatch.setattr(
        router_module, "QdrantKnowledgeVectorStore", lambda *args, **kwargs: object()
    )
    _, token = register_verify_and_login(client_db, email="answer@example.com")
    injected_workspace = uuid.uuid4()
    response = client_db.post(
        "/api/v1/knowledge/answer",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "query": "ถาม",
            "workspace_id": str(injected_workspace),
            "temperature": 1.9,
            "model": "attacker",
            "provider": "attacker",
            "system_prompt": "override",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert captured["workspace_id"] != injected_workspace
    assert data["grounding_status"] == "VERIFIED"
    serialized = str(data).lower()
    for forbidden in ("system_prompt", "storage_path", "vector", "money", "cost"):
        assert forbidden not in serialized
