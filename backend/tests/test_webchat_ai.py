"""PostgreSQL-backed WebChat AI routing and idempotency tests."""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

import app.services.action_collection as action_collection_module
import app.webchat.router as webchat_router
from app.models.conversation import Conversation
from app.models.message import Message, SenderType
from app.schemas.message import MessageCreate
from app.services.grounded_generation import GroundedAnswer, GroundingStatus
from app.services.message import MessageService
from app.services.webchat_ai import WebChatAIOrchestrator
from tests.conftest import TestSessionLocal, register_verify_and_login

URL = "/api/v1/webchat/sessions"


class FakeGroundedGeneration:
    def __init__(self) -> None:
        self.calls = 0
        self._lock = Lock()

    async def answer(self, *, workspace_id, query):
        with self._lock:
            self.calls += 1
        return GroundedAnswer(
            query=query,
            answer=f"Grounded: {query}",
            grounding_status=GroundingStatus.NO_KNOWLEDGE,
            citations=[],
            generation_skipped=True,
            model=None,
            provider=None,
            usage=None,
            prompt_version="test",
            context_version="test",
        )


def _workspace(client: TestClient, email: str) -> tuple[str, dict[str, str]]:
    data, token = register_verify_and_login(client, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    connected = client.post("/api/v1/channels/webchat", headers=headers)
    assert connected.status_code == 200
    return data["workspace"]["slug"], headers


def _session(client: TestClient, workspace_key: str) -> dict[str, str]:
    response = client.post(
        URL, json={"workspace_key": workspace_key, "name": "Visitor"}
    )
    assert response.status_code == 201
    return response.json()["data"]


def _send(client: TestClient, webchat: dict[str, str], message_id: str, content: str):
    return client.post(
        f"{URL}/{webchat['conversation_id']}/messages",
        headers={"X-WebChat-Token": webchat["session_token"]},
        json={"client_message_id": message_id, "content": content},
    )


def _install_fake_grounded(monkeypatch: pytest.MonkeyPatch) -> FakeGroundedGeneration:
    grounded = FakeGroundedGeneration()

    def factory(session, qdrant):
        return WebChatAIOrchestrator(session, grounded)

    monkeypatch.setattr(webchat_router, "create_webchat_ai_orchestrator", factory)
    return grounded


def _message_counts(conversation_id: str) -> tuple[int, int]:
    async def inspect():
        async with TestSessionLocal() as session:
            customer = await session.scalar(
                select(func.count(Message.id)).where(
                    Message.conversation_id == uuid.UUID(conversation_id),
                    Message.sender_type == SenderType.CUSTOMER,
                )
            )
            assistant = await session.scalar(
                select(func.count(Message.id)).where(
                    Message.conversation_id == uuid.UUID(conversation_id),
                    Message.sender_type == SenderType.AI,
                )
            )
            return customer or 0, assistant or 0

    return asyncio.run(inspect())


def test_same_client_message_id_returns_original_result_without_duplicate_processing(
    client_db: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    grounded = _install_fake_grounded(monkeypatch)
    workspace, _ = _workspace(client_db, "webchat-idempotent@example.com")
    webchat = _session(client_db, workspace)

    first = _send(client_db, webchat, "same-1", "first content")
    retry = _send(client_db, webchat, "same-1", "changed retry content")

    assert first.status_code == retry.status_code == 201
    assert retry.json()["data"] == first.json()["data"]
    assert grounded.calls == 1
    assert _message_counts(webchat["conversation_id"]) == (1, 1)


def test_concurrent_same_client_message_id_is_processed_once(
    client_db: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    grounded = _install_fake_grounded(monkeypatch)
    workspace, _ = _workspace(client_db, "webchat-concurrent@example.com")
    webchat = _session(client_db, workspace)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: _send(client_db, webchat, "race-1", "same request"),
                range(2),
            )
        )

    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["data"] == responses[1].json()["data"]
    assert grounded.calls == 1
    assert _message_counts(webchat["conversation_id"]) == (1, 1)


def test_action_collection_and_response_are_idempotent(
    client_db: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    grounded = _install_fake_grounded(monkeypatch)
    workspace, headers = _workspace(client_db, "webchat-action@example.com")
    created = client_db.post(
        "/api/v1/actions/definitions",
        headers=headers,
        json={
            "key": "support_ticket",
            "name": "Support ticket",
            "required_fields": [
                {
                    "key": "subject",
                    "label": "Subject",
                    "type": "string",
                    "required": True,
                }
            ],
        },
    )
    assert created.status_code == 201
    calls = 0
    original = action_collection_module.ActionCollectionService.create

    async def counted_create(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(
        action_collection_module.ActionCollectionService, "create", counted_create
    )
    webchat = _session(client_db, workspace)
    content = 'action:support_ticket {"subject":"Cannot log in"}'

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, retry = list(
            pool.map(
                lambda _: _send(client_db, webchat, "action-1", content), range(2)
            )
        )

    assert first.status_code == retry.status_code == 201
    assert retry.json()["data"] == first.json()["data"]
    assert first.json()["data"]["assistant"]["type"] == "ACTION_CONFIRMATION"
    assert calls == 1
    assert grounded.calls == 0
    assert _message_counts(webchat["conversation_id"]) == (1, 1)


def test_message_uniqueness_scope_null_behavior_and_non_webchat_creation(
    client_db: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_grounded(monkeypatch)
    workspace, _ = _workspace(client_db, "webchat-constraint@example.com")
    first_chat = _session(client_db, workspace)
    second_chat = _session(client_db, workspace)
    assert _send(client_db, first_chat, "shared-id", "one").status_code == 201
    assert _send(client_db, second_chat, "shared-id", "two").status_code == 201

    async def exercise_database_constraint():
        async with TestSessionLocal() as session:
            service = MessageService(session)
            conversation_id = uuid.UUID(first_chat["conversation_id"])
            conversation = await session.get(Conversation, conversation_id)
            assert conversation is not None
            for content in ("legacy one", "legacy two"):
                await service.create_message(
                    conversation.workspace_id,
                    conversation_id,
                    MessageCreate(sender_type=SenderType.SYSTEM, content=content),
                )
            with pytest.raises(IntegrityError):
                await service.create_message(
                    conversation.workspace_id,
                    conversation_id,
                    MessageCreate(
                        sender_type=SenderType.SYSTEM,
                        content="duplicate",
                        external_message_id="shared-id",
                    ),
                )

    asyncio.run(exercise_database_constraint())
    assert _message_counts(first_chat["conversation_id"]) == (1, 1)
