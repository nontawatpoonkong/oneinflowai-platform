import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.demo.router import get_demo_chat_service
from app.integrations.generation import GenerationResult
from app.main import app
from app.models.action import ActionRequest
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.message import Message
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.workspace import Workspace
from app.schemas.demo import DemoChatRequest, DemoChatResponse
from app.services.demo_chat import PUBLIC_DEMO_FILES, DemoChatService
from app.services.public_rate_limit import PublicRateLimitService


class RecordingProvider:
    name = "test"

    def __init__(self, text: str = "OneInFlow supports WebChat. [S1]") -> None:
        self.text = text
        self.calls = []

    async def generate(self, prompt):
        self.calls.append(prompt)
        return GenerationResult(text=self.text, model="test", provider="test")


class AtomicFakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.keys: list[str] = []
        self.lock = asyncio.Lock()

    async def eval(self, script, key_count, key, window):
        async with self.lock:
            self.keys.append(key)
            self.counts[key] = self.counts.get(key, 0) + 1
            return [self.counts[key], window]

    async def aclose(self):
        return None


class UnavailableRedis:
    async def eval(self, *args):
        raise RedisConnectionError("private redis detail")


class StubDemoService:
    def __init__(self) -> None:
        self.calls = 0

    async def answer(self, payload):
        self.calls += 1
        return DemoChatResponse(
            answer="OneInFlow supports WebChat. [S1]",
            citations=[{"label": "S1", "source": "README.md"}],
        )


async def operational_record_counts() -> tuple[int, ...]:
    models = (
        Workspace,
        Customer,
        Conversation,
        Message,
        ActionRequest,
        Payment,
        Notification,
    )
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://oneflowai:oneflowai@localhost:5432/oneflowai_test",
    )
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            counts = []
            for model in models:
                value = await session.scalar(select(func.count()).select_from(model))
                counts.append(int(value or 0))
            return tuple(counts)
    finally:
        await engine.dispose()


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    path = tmp_path / "public.md"
    path.write_text(
        "# Public\n\nSource: README.md\n\nOneInFlow supports WebChat and LINE.\n\n"
        "Source: docs/06_ROADMAP.md\n\nInstagram is planned.",
        encoding="utf-8",
    )
    return path


@pytest.mark.asyncio
async def test_demo_chat_is_stateless_and_returns_allowlisted_citation(corpus):
    provider = RecordingProvider()
    service = DemoChatService(provider, corpus_path=corpus)

    result = await service.answer(DemoChatRequest(message="WebChat"))

    assert result.answer == "OneInFlow supports WebChat. [S1]"
    assert result.citations[0].source == "README.md"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_demo_chat_skips_generation_when_public_corpus_has_no_match(corpus):
    provider = RecordingProvider()
    service = DemoChatService(provider, corpus_path=corpus)

    result = await service.answer(DemoChatRequest(message="quantum banana"))

    assert result.citations == []
    assert provider.calls == []


@pytest.mark.asyncio
async def test_demo_chat_fails_closed_when_model_omits_citation(corpus):
    provider = RecordingProvider("Unsupported answer")
    result = await DemoChatService(provider, corpus_path=corpus).answer(
        DemoChatRequest(message="WebChat")
    )

    assert result.citations == []
    assert "ยืนยัน" in result.answer


def test_demo_chat_request_caps_history():
    with pytest.raises(ValueError):
        DemoChatRequest(
            message="WebChat",
            history=[{"role": "user", "content": "x"}] * 9,
        )


def test_demo_chat_request_length_is_bounded():
    with pytest.raises(ValueError):
        DemoChatRequest(message="x" * 1001)


@pytest.mark.asyncio
async def test_atomic_limiter_allows_limit_and_blocks_concurrent_excess():
    redis = AtomicFakeRedis()
    limiter = PublicRateLimitService(redis, requests=5, window_seconds=60)

    results = await asyncio.gather(
        *(limiter.check("demo-chat", "127.0.0.1") for _ in range(12))
    )

    assert sum(result.allowed for result in results) == 5
    assert all(result.retry_after_seconds == 60 for result in results)
    assert "127.0.0.1" not in redis.keys[0]


@pytest.mark.asyncio
async def test_rate_limit_keys_are_isolated_by_direct_client_ip():
    redis = AtomicFakeRedis()
    limiter = PublicRateLimitService(redis, requests=1, window_seconds=60)

    first = await limiter.check("demo-chat", "192.0.2.1")
    second = await limiter.check("demo-chat", "192.0.2.2")

    assert first.allowed and second.allowed
    assert first.identity_hash != second.identity_hash


def test_over_limit_returns_429_and_does_not_call_llm(client: TestClient):
    service = StubDemoService()
    app.dependency_overrides[get_demo_chat_service] = lambda: service
    client.app.state.redis = AtomicFakeRedis()
    try:
        responses = [
            client.post("/api/v1/demo/chat", json={"message": "WebChat"})
            for _ in range(6)
        ]
    finally:
        app.dependency_overrides.pop(get_demo_chat_service, None)

    assert [response.status_code for response in responses] == [200] * 5 + [429]
    assert responses[-1].json()["error"]["code"] == "DEMO_RATE_LIMIT_EXCEEDED"
    assert int(responses[-1].headers["Retry-After"]) >= 1
    assert service.calls == 5


def test_redis_unavailable_returns_503_and_does_not_call_llm(client: TestClient):
    service = StubDemoService()
    app.dependency_overrides[get_demo_chat_service] = lambda: service
    client.app.state.redis = UnavailableRedis()
    try:
        response = client.post("/api/v1/demo/chat", json={"message": "WebChat"})
    finally:
        app.dependency_overrides.pop(get_demo_chat_service, None)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEMO_RATE_LIMIT_UNAVAILABLE"
    assert "redis" not in response.text.lower()
    assert service.calls == 0


def test_invalid_input_never_calls_llm(client: TestClient):
    service = StubDemoService()
    app.dependency_overrides[get_demo_chat_service] = lambda: service
    client.app.state.redis = AtomicFakeRedis()
    try:
        response = client.post("/api/v1/demo/chat", json={"message": "x" * 1001})
    finally:
        app.dependency_overrides.pop(get_demo_chat_service, None)

    assert response.status_code == 422
    assert service.calls == 0


def test_demo_creates_no_database_records(client_db: TestClient):
    service = StubDemoService()
    app.dependency_overrides[get_demo_chat_service] = lambda: service
    client_db.app.state.redis = AtomicFakeRedis()
    before = asyncio.run(operational_record_counts())
    try:
        response = client_db.post(
            "/api/v1/demo/chat", json={"message": "WebChat"}
        )
    finally:
        app.dependency_overrides.pop(get_demo_chat_service, None)
    after = asyncio.run(operational_record_counts())

    assert response.status_code == 200
    assert before == after == (0, 0, 0, 0, 0, 0, 0)


def test_demo_corpus_allowlist_is_exact():
    assert PUBLIC_DEMO_FILES == (
        "README.md",
        "docs/01_PRODUCT_SPEC.md",
        "docs/06_ROADMAP.md",
        "docs/10_CHANNEL_INTEGRATIONS.md",
        "docs/11_MVP_OPERATIONS.md",
    )
