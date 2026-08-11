"""Channel connection and credential-security tests."""

import base64
import logging
import uuid

import pytest

from app.core.channels import ChannelType
from app.core.config import Settings
from app.integrations.channels.security import (
    ChannelCredentialCipher,
    ChannelCredentialSecurityError,
    EncryptedCredentialBundle,
)
from tests.conftest import register_verify_and_login


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
