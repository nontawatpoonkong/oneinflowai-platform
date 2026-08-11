"""Deterministic Facebook Messenger adapter tests."""

import hashlib
import hmac

from app.integrations.channels.facebook import FacebookMessengerChannelProvider
from app.integrations.channels.provider import ChannelSendResult
from tests.conftest import register_verify_and_login


def test_facebook_signature_handshake_normalization_and_echo_safety():
    provider = FacebookMessengerChannelProvider(
        {
            "page_access_token": "token",
            "app_secret": "secret",
            "verify_token": "verification-value",
        }
    )
    body = b'{"entry":[]}'
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert provider.verify_signature(body, signature)
    assert not provider.verify_signature(body, "sha256=bad")
    assert provider.verify_token("verification-value")
    assert not provider.verify_token("wrong")
    items = provider.parse(
        {
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "PSID"},
                            "message": {"mid": "mid.1", "text": "hello"},
                        },
                        {
                            "sender": {"id": "PAGE"},
                            "message": {
                                "mid": "mid.echo",
                                "text": "reply",
                                "is_echo": True,
                            },
                        },
                    ]
                }
            ]
        }
    )
    assert len(items) == 1
    assert items[0].external_user_id == "PSID"
    assert items[0].external_message_id == "mid.1"


def test_facebook_webhook_handshake_auth_echo_and_idempotency(client_db, monkeypatch):
    import json

    _, token = register_verify_and_login(client_db, email="facebook@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = client_db.post(
        "/api/v1/channels/facebook",
        headers=headers,
        json={
            "display_name": "Facebook",
            "external_account_id": "PAGE-1",
            "page_access_token": "page-token",
            "app_secret": "app-secret",
            "verify_token": "verify-token-value",
        },
    )
    assert created.status_code == 201
    connection_id = created.json()["data"]["id"]
    verify_url = f"/api/v1/channels/webhooks/facebook/{connection_id}"
    verified = client_db.get(
        verify_url,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-token-value",
            "hub.challenge": "challenge-value",
        },
    )
    assert verified.status_code == 200
    assert verified.text == "challenge-value"
    assert (
        client_db.get(
            verify_url,
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-value-here",
                "hub.challenge": "challenge",
            },
        ).status_code
        == 401
    )
    sends = []

    async def fake_send(self, message):
        sends.append(message)
        return ChannelSendResult("fb-out-1")

    monkeypatch.setattr(FacebookMessengerChannelProvider, "send", fake_send)
    payload = {
        "entry": [
            {
                "messaging": [
                    {
                        "sender": {"id": "PSID-1"},
                        "message": {
                            "mid": "fb-mid-1",
                            "text": "talk to a human",
                        },
                    },
                    {
                        "sender": {"id": "PAGE-1"},
                        "message": {
                            "mid": "echo-1",
                            "text": "assistant",
                            "is_echo": True,
                        },
                    },
                ]
            }
        ]
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    webhook_headers = {
        "X-Hub-Signature-256": signature,
        "Content-Type": "application/json",
    }
    first = client_db.post(verify_url, content=body, headers=webhook_headers)
    assert first.status_code == 200, first.text
    assert (
        client_db.post(verify_url, content=body, headers=webhook_headers).status_code
        == 200
    )
    assert len(sends) == 1
    conversation = client_db.get(
        "/api/v1/conversations", headers=headers
    ).json()["data"]["items"][0]
    assert conversation["channel"] == "facebook"
    assert conversation["ai_mode"] == "HUMAN"
