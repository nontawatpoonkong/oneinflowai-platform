"""PostgreSQL-backed shared channel ingestion and delivery tests."""

import base64
import hashlib
import hmac

from app.integrations.channels.line import LineChannelProvider
from app.integrations.channels.provider import (
    ChannelProviderError,
    ChannelProviderErrorCode,
    ChannelSendResult,
)
from tests.conftest import register_verify_and_login


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _line_connection(client, token):
    response = client.post(
        "/api/v1/channels/line",
        headers=_headers(token),
        json={
            "display_name": "LINE",
            "external_account_id": "line-page",
            "channel_access_token": "token",
            "channel_secret": "secret",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def _line_webhook(client, connection_id, payload):
    import json

    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = base64.b64encode(
        hmac.new(b"secret", body, hashlib.sha256).digest()
    ).decode()
    return client.post(
        f"/api/v1/channels/webhooks/line/{connection_id}",
        content=body,
        headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
    )


def test_line_shared_ingestion_identity_idempotency_and_sent_delivery(
    client_db, monkeypatch
):
    _, token = register_verify_and_login(client_db, email="line-core@example.com")
    connection = _line_connection(client_db, token)
    sends = []

    async def fake_send(self, message):
        sends.append(message)
        return ChannelSendResult("provider-message-1")

    monkeypatch.setattr(LineChannelProvider, "send", fake_send)
    payload = {
        "events": [
            {
                "type": "message",
                "source": {"userId": "LINE-U1"},
                "message": {
                    "id": "line-mid-1",
                    "type": "text",
                    "text": "talk to a human",
                },
            }
        ]
    }
    first = _line_webhook(client_db, connection["id"], payload)
    assert first.status_code == 200, first.text
    first = _line_webhook(client_db, connection["id"], payload)
    assert first.status_code == 200, first.text
    assert len(sends) == 1
    follow_up = {
        "events": [
            {
                "type": "message",
                "source": {"userId": "LINE-U1"},
                "message": {
                    "id": "line-mid-2",
                    "type": "text",
                    "text": "no automatic reply",
                },
            }
        ]
    }
    assert _line_webhook(client_db, connection["id"], follow_up).status_code == 200
    assert len(sends) == 1
    conversations = client_db.get(
        "/api/v1/conversations", headers=_headers(token)
    ).json()["data"]["items"]
    assert len(conversations) == 1
    assert conversations[0]["channel"] == "line"
    assert conversations[0]["ai_mode"] == "HUMAN"
    messages = client_db.get(
        f"/api/v1/conversations/{conversations[0]['id']}/messages",
        headers=_headers(token),
    ).json()["data"]["items"]
    assert len([item for item in messages if item["sender_type"] == "customer"]) == 2
    assert len([item for item in messages if item["sender_type"] == "ai"]) == 1


def test_provider_failure_is_failed_and_staff_reply_reports_truthfully(
    client_db, monkeypatch
):
    _, token = register_verify_and_login(client_db, email="line-fail@example.com")
    connection = _line_connection(client_db, token)

    async def fail_send(self, message):
        raise ChannelProviderError(ChannelProviderErrorCode.NETWORK_ERROR)

    monkeypatch.setattr(LineChannelProvider, "send", fail_send)
    payload = {
        "events": [
            {
                "type": "message",
                "source": {"userId": "LINE-U2"},
                "message": {"id": "line-mid-2", "type": "text", "text": "hello"},
            }
        ]
    }
    assert _line_webhook(client_db, connection["id"], payload).status_code == 200
    conversation = client_db.get(
        "/api/v1/conversations", headers=_headers(token)
    ).json()["data"]["items"][0]
    reply = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=_headers(token),
        json={"sender_type": "agent", "content": "staff reply"},
    )
    assert reply.status_code == 201
    assert reply.json()["data"]["delivery"] == {
        "status": "FAILED",
        "provider_message_id": None,
        "last_error_code": "NETWORK_ERROR",
        "sent_at": None,
    }


def test_invalid_line_signature_and_disconnected_connection_rejected(client_db):
    _, token = register_verify_and_login(client_db, email="line-sec@example.com")
    connection = _line_connection(client_db, token)
    url = f"/api/v1/channels/webhooks/line/{connection['id']}"
    assert (
        client_db.post(
            url, content=b"{}", headers={"X-Line-Signature": "bad"}
        ).status_code
        == 401
    )
    client_db.delete(
        f"/api/v1/channels/connections/{connection['id']}", headers=_headers(token)
    )
    assert _line_webhook(client_db, connection["id"], {"events": []}).status_code == 401
