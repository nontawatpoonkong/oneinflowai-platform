"""Facebook Page Messenger transport adapter."""

import hashlib
import hmac

import httpx

from app.core.channels import ChannelType
from app.integrations.channels.provider import (
    ChannelInboundMessage,
    ChannelOutboundMessage,
    ChannelProviderError,
    ChannelProviderErrorCode,
    ChannelSendResult,
)


class FacebookMessengerChannelProvider:
    provider = ChannelType.FACEBOOK
    api_url = "https://graph.facebook.com/v23.0/me/messages"

    def __init__(self, credentials: dict[str, str], *, timeout: float = 10) -> None:
        self.credentials = credentials
        self.timeout = timeout

    def verify_signature(self, body: bytes, signature: str) -> bool:
        expected = (
            "sha256="
            + hmac.new(
                self.credentials["app_secret"].encode(), body, hashlib.sha256
            ).hexdigest()
        )
        return hmac.compare_digest(expected, signature)

    def verify_token(self, token: str) -> bool:
        return hmac.compare_digest(self.credentials["verify_token"], token)

    def parse(self, payload: dict) -> list[ChannelInboundMessage]:
        messages = []
        for entry in payload.get("entry", []):
            for event in entry.get("messaging", []):
                message = event.get("message") or {}
                sender = event.get("sender") or {}
                if message.get("is_echo") or not message.get("text"):
                    continue
                if not sender.get("id") or not message.get("mid"):
                    continue
                messages.append(
                    ChannelInboundMessage(
                        provider=self.provider,
                        external_user_id=str(sender["id"]),
                        external_message_id=str(message["mid"]),
                        text=str(message["text"]),
                    )
                )
        return messages

    async def send(self, message: ChannelOutboundMessage) -> ChannelSendResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    params={"access_token": self.credentials["page_access_token"]},
                    json={
                        "recipient": {"id": message.external_user_id},
                        "message": {"text": message.text},
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
        data = response.json()
        return ChannelSendResult(data.get("message_id"))
