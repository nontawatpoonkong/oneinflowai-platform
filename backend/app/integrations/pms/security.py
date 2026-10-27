"""AES-256-GCM PMS credential encryption with Workspace-bound AAD."""

import base64
import binascii
import json
import os
import uuid
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings, get_settings


class PMSCredentialSecurityError(Exception):
    pass


@dataclass(frozen=True)
class EncryptedPMSCredentials:
    ciphertext: bytes
    nonce: bytes
    key_version: str


class PMSCredentialCipher:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _key(self) -> bytes:
        encoded = self.settings.CHANNEL_CREDENTIAL_ENCRYPTION_KEY
        if not encoded:
            raise PMSCredentialSecurityError()
        try:
            key = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise PMSCredentialSecurityError() from exc
        if len(key) != 32:
            raise PMSCredentialSecurityError()
        return key

    @staticmethod
    def aad(workspace_id: uuid.UUID, connection_id: uuid.UUID, provider: str) -> bytes:
        return f"pms:{workspace_id}:{connection_id}:{provider.lower()}".encode()

    def encrypt(self, value: dict[str, str], *, workspace_id, connection_id, provider):
        if not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in value.items()
        ):
            raise PMSCredentialSecurityError()
        nonce = os.urandom(12)
        plaintext = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ciphertext = AESGCM(self._key()).encrypt(
            nonce, plaintext, self.aad(workspace_id, connection_id, provider)
        )
        return EncryptedPMSCredentials(
            ciphertext, nonce, self.settings.CHANNEL_CREDENTIAL_KEY_VERSION
        )

    def decrypt(self, encrypted, *, workspace_id, connection_id, provider):
        if encrypted.key_version != self.settings.CHANNEL_CREDENTIAL_KEY_VERSION:
            raise PMSCredentialSecurityError()
        try:
            plaintext = AESGCM(self._key()).decrypt(
                encrypted.nonce,
                encrypted.ciphertext,
                self.aad(workspace_id, connection_id, provider),
            )
            value = json.loads(plaintext)
        except (InvalidTag, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PMSCredentialSecurityError() from exc
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in value.items()
        ):
            raise PMSCredentialSecurityError()
        return value
