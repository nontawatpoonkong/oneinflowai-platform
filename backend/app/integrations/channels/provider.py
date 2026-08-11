"""Normalized provider-neutral channel contracts and provider errors."""

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.channels import ChannelType


class ChannelProviderErrorCode(enum.StrEnum):
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_WEBHOOK_SIGNATURE = "INVALID_WEBHOOK_SIGNATURE"
    UNSUPPORTED_EVENT = "UNSUPPORTED_EVENT"


class ChannelProviderError(Exception):
    def __init__(self, code: ChannelProviderErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True)
class ChannelInboundMessage:
    provider: ChannelType
    external_user_id: str
    external_message_id: str
    text: str
    timestamp: datetime | None = None
    external_conversation_id: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class ChannelOutboundMessage:
    provider: ChannelType
    external_user_id: str
    text: str
    external_conversation_id: str | None = None
    reply_to_external_message_id: str | None = None


@dataclass(frozen=True)
class ChannelSendResult:
    provider_message_id: str | None = None


class ChannelProvider(Protocol):
    provider: ChannelType

    def verify_signature(self, body: bytes, signature: str) -> bool: ...

    def parse(self, payload: dict) -> list[ChannelInboundMessage]: ...

    async def send(self, message: ChannelOutboundMessage) -> ChannelSendResult: ...
