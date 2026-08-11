"""LINE Messaging API transport adapter."""

import base64
import hashlib
import hmac
from datetime import UTC, datetime

import httpx

from app.core.channels import ChannelType
from app.integrations.channels.provider import (
    ChannelInboundMessage,
    ChannelOutboundMessage,
    ChannelProviderError,
    ChannelProviderErrorCode,
    ChannelSendResult,
)


class LineChannelProvider:
    provider = ChannelType.LINE
    api_url = "https://api.line.me/v2/bot/message/push"

    def __init__(self, credentials: dict[str, str], *, timeout: float = 10) -> None:
        self.credentials = credentials
        self.timeout = timeout

    def verify_signature(self, body: bytes, signature: str) -> bool:
        expected = base64.b64encode(
            hmac.new(
                self.credentials["channel_secret"].encode(), body, hashlib.sha256
            ).digest()
        ).decode()
        return hmac.compare_digest(expected, signature)

    def parse(self, payload: dict) -> list[ChannelInboundMessage]:
        messages = []
        for event in payload.get("events", []):
            if event.get("type") != "message":
                continue
            message = event.get("message") or {}
            source = event.get("source") or {}
            if message.get("type") != "text" or not source.get("userId"):
                continue
            messages.append(
                ChannelInboundMessage(
                    provider=self.provider,
                    external_user_id=source["userId"],
                    external_message_id=str(message.get("id", "")),
                    external_conversation_id=source.get("groupId")
                    or source.get("roomId"),
                    text=str(message.get("text", "")),
                    timestamp=datetime.fromtimestamp(event["timestamp"] / 1000, UTC)
                    if event.get("timestamp")
                    else None,
                )
            )
        return [item for item in messages if item.external_message_id and item.text]

    async def send(self, message: ChannelOutboundMessage) -> ChannelSendResult:
        headers = {
            "Authorization": f"Bearer {self.credentials['channel_access_token']}"
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json={
                        "to": message.external_user_id,
                        "messages": [{"type": "text", "text": message.text}],
                    },
                )
        except httpx.TimeoutException as exc:
            raise ChannelProviderError(ChannelProviderErrorCode.TIMEOUT) from exc
        except httpx.NetworkError as exc:
            raise ChannelProviderError(ChannelProviderErrorCode.NETWORK_ERROR) from exc
        if response.status_code in {401, 403}:
            raise ChannelProviderError(ChannelProviderErrorCode.AUTHENTICATION_FAILED)
        if response.status_code == 429:
            raise ChannelProviderError(ChannelProviderErrorCode.RATE_LIMITED)
        if response.is_error:
            raise ChannelProviderError(ChannelProviderErrorCode.PROVIDER_ERROR)
        return ChannelSendResult(response.headers.get("x-line-request-id"))
