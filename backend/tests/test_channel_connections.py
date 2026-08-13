"""Channel connection and credential-security tests."""

import asyncio
import base64
import logging
import uuid

import pytest
from sqlalchemy import func, select

from app.core.channels import ChannelType
from app.core.config import Settings
from app.demo.router import get_demo_chat_service
from app.integrations.channels.security import (
    ChannelCredentialCipher,
    ChannelCredentialSecurityError,
    EncryptedCredentialBundle,
)
from app.main import app
from app.models.channel import ChannelConnection
from app.models.conversation import Conversation
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.demo import DemoChatResponse
from tests.conftest import TestSessionLocal, register_verify_and_login


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _set_role(user_id: str, role: WorkspaceRole) -> None:
    async def _update() -> None:
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.user_id == uuid.UUID(user_id)
                )
            )
            assert membership is not None
            membership.role = role
            await session.commit()

    asyncio.run(_update())


def _settings(key: bytes | None = b"a" * 32):
    return Settings(
        CHANNEL_CREDENTIAL_ENCRYPTION_KEY=(
            base64.b64encode(key).decode() if key is not None else None
        )
    )


def test_aes_gcm_roundtrip_random_nonce_and_fail_closed():
    workspace_id, connection_id = uuid.uuid4(), uuid.uuid4()
    bundle = {"channel_access_token": "not-real", "channel_secret": "secret"}
    cipher = ChannelCredentialCipher(_settings())
    first = cipher.encrypt(
        bundle,
        workspace_id=workspace_id,
        connection_id=connection_id,
        provider=ChannelType.LINE,
    )
    second = cipher.encrypt(
        bundle,
        workspace_id=workspace_id,
        connection_id=connection_id,
        provider=ChannelType.LINE,
    )
    assert first.ciphertext != second.ciphertext
    assert (
        cipher.decrypt(
            first,
            workspace_id=workspace_id,
            connection_id=connection_id,
            provider=ChannelType.LINE,
        )
        == bundle
    )
    for bad in (
        ChannelCredentialCipher(_settings(b"b" * 32)),
        ChannelCredentialCipher(_settings(None)),
        ChannelCredentialCipher(
            Settings(CHANNEL_CREDENTIAL_ENCRYPTION_KEY="not-base64")
        ),
        ChannelCredentialCipher(_settings(b"short")),
    ):
        with pytest.raises(ChannelCredentialSecurityError):
            bad.decrypt(
                first,
                workspace_id=workspace_id,
                connection_id=connection_id,
                provider=ChannelType.LINE,
            )
    with pytest.raises(ChannelCredentialSecurityError):
        cipher.decrypt(
            first,
            workspace_id=uuid.uuid4(),
            connection_id=connection_id,
            provider=ChannelType.LINE,
        )
    tampered = EncryptedCredentialBundle(
        first.ciphertext[:-1] + bytes([first.ciphertext[-1] ^ 1]),
        first.nonce,
        first.key_version,
    )
    with pytest.raises(ChannelCredentialSecurityError):
        cipher.decrypt(
            tampered,
            workspace_id=workspace_id,
            connection_id=connection_id,
            provider=ChannelType.LINE,
        )


def test_channel_connections_are_isolated_and_never_return_secrets(client_db, caplog):
    owner, token = register_verify_and_login(client_db, email="channels-a@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "display_name": "LINE Main",
        "external_account_id": "line-account",
        "channel_access_token": "test-access-token-never-return",
        "channel_secret": "test-channel-secret-never-return",
    }
    with caplog.at_level(logging.DEBUG):
        created = client_db.post("/api/v1/channels/line", json=payload, headers=headers)
    assert created.status_code == 201
    body = created.text
    assert payload["channel_access_token"] not in body
    assert payload["channel_secret"] not in body
    assert payload["channel_access_token"] not in caplog.text
    connection_id = created.json()["data"]["id"]
    assert (
        client_db.get("/api/v1/channels", headers=headers).json()["data"][0][
            "workspace_id"
        ]
        == owner["workspace"]["id"]
    )

    _, other_token = register_verify_and_login(
        client_db, email="channels-b@example.com"
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert (
        client_db.get(
            f"/api/v1/channels/connections/{connection_id}", headers=other_headers
        ).status_code
        == 404
    )


def test_new_workspace_has_no_automatic_webchat_connection(client_db):
    _, token = register_verify_and_login(client_db, email="web-new@example.com")
    response = client_db.get("/api/v1/channels", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize("role", [WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
def test_owner_and_admin_connect_webchat_idempotently(client_db, role):
    registered, token = register_verify_and_login(
        client_db, email=f"web-{role.value}@example.com"
    )
    _set_role(registered["user"]["id"], role)
    headers = _auth(token)

    first = client_db.post("/api/v1/channels/webchat", headers=headers)
    second = client_db.post("/api/v1/channels/webchat", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert first.json()["data"]["provider"] == "web"
    assert first.json()["data"]["status"] == "CONNECTED"
    listed = client_db.get("/api/v1/channels", headers=headers).json()["data"]
    assert [item["provider"] for item in listed] == ["web"]


def test_member_cannot_connect_webchat(client_db):
    registered, token = register_verify_and_login(
        client_db, email="web-member@example.com"
    )
    _set_role(registered["user"]["id"], WorkspaceRole.MEMBER)
    response = client_db.post("/api/v1/channels/webchat", headers=_auth(token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_webchat_disconnect_reconnect_and_workspace_isolation(client_db):
    workspace_a, token_a = register_verify_and_login(
        client_db, email="web-isolation-a@example.com"
    )
    headers_a = _auth(token_a)
    connected = client_db.post("/api/v1/channels/webchat", headers=headers_a)
    connection_id = connected.json()["data"]["id"]

    workspace_b, token_b = register_verify_and_login(
        client_db, email="web-isolation-b@example.com"
    )
    headers_b = _auth(token_b)
    assert client_db.get("/api/v1/channels", headers=headers_b).json()["data"] == []
    assert (
        client_db.delete(
            f"/api/v1/channels/connections/{connection_id}", headers=headers_b
        ).status_code
        == 404
    )
    blocked = client_db.post(
        "/api/v1/webchat/sessions",
        json={"workspace_key": workspace_b["workspace"]["slug"], "name": "Visitor"},
    )
    assert blocked.status_code == 409

    disconnected = client_db.delete(
        f"/api/v1/channels/connections/{connection_id}", headers=headers_a
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["data"]["status"] == "DISCONNECTED"
    blocked = client_db.post(
        "/api/v1/webchat/sessions",
        json={"workspace_key": workspace_a["workspace"]["slug"], "name": "Visitor"},
    )
    assert blocked.status_code == 409

    reconnected = client_db.post("/api/v1/channels/webchat", headers=headers_a)
    assert reconnected.status_code == 200
    assert reconnected.json()["data"]["id"] == connection_id
    assert reconnected.json()["data"]["status"] == "CONNECTED"

    connected_b = client_db.post("/api/v1/channels/webchat", headers=headers_b)
    assert connected_b.status_code == 200
    assert connected_b.json()["data"]["id"] != connection_id
    session_b = client_db.post(
        "/api/v1/webchat/sessions",
        json={"workspace_key": workspace_b["workspace"]["slug"], "name": "Visitor"},
    )
    assert session_b.status_code == 201

    async def _connection_for_b() -> uuid.UUID | None:
        async with TestSessionLocal() as session:
            conversation = await session.get(
                Conversation, uuid.UUID(session_b.json()["data"]["conversation_id"])
            )
            assert conversation is not None
            return conversation.channel_connection_id

    assert asyncio.run(_connection_for_b()) == uuid.UUID(
        connected_b.json()["data"]["id"]
    )


def test_disconnect_preserves_historical_webchat_conversation(client_db):
    workspace, token = register_verify_and_login(
        client_db, email="web-history@example.com"
    )
    headers = _auth(token)
    connection = client_db.post("/api/v1/channels/webchat", headers=headers).json()[
        "data"
    ]
    created = client_db.post(
        "/api/v1/webchat/sessions",
        json={"workspace_key": workspace["workspace"]["slug"], "name": "Visitor"},
    )
    assert created.status_code == 201
    conversation_id = uuid.UUID(created.json()["data"]["conversation_id"])
    assert (
        client_db.delete(
            f"/api/v1/channels/connections/{connection['id']}", headers=headers
        ).status_code
        == 200
    )

    async def _count() -> tuple[int, int]:
        async with TestSessionLocal() as session:
            conversations = await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.channel_connection_id == uuid.UUID(connection["id"]),
                )
            )
            connections = await session.scalar(
                select(func.count())
                .select_from(ChannelConnection)
                .where(ChannelConnection.id == uuid.UUID(connection["id"]))
            )
            return int(conversations or 0), int(connections or 0)

    assert asyncio.run(_count()) == (1, 1)


def test_public_demo_does_not_create_webchat_connection(client_db):
    _, token = register_verify_and_login(client_db, email="demo-isolated@example.com")

    class _Demo:
        async def answer(self, request):
            return DemoChatResponse(answer="Demo only", citations=[])

    app.dependency_overrides[get_demo_chat_service] = _Demo
    response = client_db.post(
        "/api/v1/demo/chat",
        json={"message": "What is OneInFlow?"},
    )
    assert response.status_code == 200
    assert client_db.get("/api/v1/channels", headers=_auth(token)).json()["data"] == []
