"""AES-GCM credential bundle encryption with tenant-bound AAD."""

import base64
import binascii
import json
import os
import uuid
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.channels import ChannelType
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError


class ChannelCredentialSecurityError(AppError):
    status_code = 500
    code = "CHANNEL_CREDENTIAL_SECURITY_ERROR"
    message = "Channel credentials are unavailable"


@dataclass(frozen=True)
class EncryptedCredentialBundle:
    ciphertext: bytes
    nonce: bytes
    key_version: str


class ChannelCredentialCipher:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _key(self) -> bytes:
        encoded = self.settings.CHANNEL_CREDENTIAL_ENCRYPTION_KEY
        if not encoded:
            raise ChannelCredentialSecurityError()
        try:
            key = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ChannelCredentialSecurityError() from exc
        if len(key) != 32:
            raise ChannelCredentialSecurityError()
        return key

    @staticmethod
    def aad(
        workspace_id: uuid.UUID, connection_id: uuid.UUID, provider: ChannelType
    ) -> bytes:
        return f"{workspace_id}:{connection_id}:{provider.value}".encode()

    def encrypt(self, bundle: dict[str, str], *, workspace_id, connection_id, provider):
        nonce = os.urandom(12)
        plaintext = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
        ciphertext = AESGCM(self._key()).encrypt(
            nonce, plaintext, self.aad(workspace_id, connection_id, provider)
        )
        return EncryptedCredentialBundle(
            ciphertext, nonce, self.settings.CHANNEL_CREDENTIAL_KEY_VERSION
        )

    def decrypt(self, encrypted, *, workspace_id, connection_id, provider):
        if encrypted.key_version != self.settings.CHANNEL_CREDENTIAL_KEY_VERSION:
            raise ChannelCredentialSecurityError()
        try:
            plaintext = AESGCM(self._key()).decrypt(
                encrypted.nonce,
                encrypted.ciphertext,
                self.aad(workspace_id, connection_id, provider),
            )
            value = json.loads(plaintext)
        except (InvalidTag, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ChannelCredentialSecurityError() from exc
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in value.items()
        ):
            raise ChannelCredentialSecurityError()
        return value
