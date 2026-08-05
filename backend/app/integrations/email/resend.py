"""Transactional email delivery through the official Resend SDK."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import resend
from resend.exceptions import ResendError

from app.core.logging import get_logger
from app.integrations.email.base import (
    EmailAuthenticationError,
    EmailDeliveryError,
    EmailNetworkError,
    EmailProvider,
    EmailProviderServerError,
    EmailRateLimitError,
)
from app.integrations.email.templates import (
    VerificationEmailContent,
    build_password_reset_email,
    build_verification_email,
)

logger = get_logger(__name__)

ResendSendCallable = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ResendEmailProvider(EmailProvider):
    """Send verification messages without exposing sensitive message data."""

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        from_name: str,
        send_async: ResendSendCallable | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender = f"{from_name} <{from_address}>"
        self._send_async = send_async or resend.Emails.send_async

    async def send_verification_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_seconds: int,
    ) -> None:
        content = build_verification_email(
            otp=otp,
            expires_in_seconds=expires_in_seconds,
        )
        await self._send(recipient=recipient, content=content)

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_seconds: int,
    ) -> None:
        content = build_password_reset_email(
            otp=otp,
            expires_in_seconds=expires_in_seconds,
        )
        await self._send(recipient=recipient, content=content)

    async def _send(
        self, *, recipient: str, content: VerificationEmailContent
    ) -> None:
        payload = {
            "from": self._sender,
            "to": [recipient],
            "subject": content.subject,
            "text": content.text,
            "html": content.html,
        }

        try:
            resend.api_key = self._api_key
            response = await self._send_async(payload)
        except ResendError as exc:
            raise _map_resend_error(exc) from None
        except (httpx.TimeoutException, TimeoutError):
            raise EmailNetworkError("Email provider request timed out") from None
        except (httpx.NetworkError, OSError):
            raise EmailNetworkError("Email provider is unavailable") from None
        except Exception:
            raise EmailDeliveryError("Email provider delivery failed") from None

        message_id = response.get("id") if isinstance(response, dict) else None
        logger.info(
            "transactional_email_sent",
            extra={
                "event": "transactional_email_sent",
                "provider": "resend",
                "message_id": message_id,
            },
        )


def _map_resend_error(exc: ResendError) -> EmailDeliveryError:
    try:
        status_code = int(exc.code)
    except (TypeError, ValueError):
        status_code = 0

    if status_code in {401, 403}:
        return EmailAuthenticationError("Email provider authentication failed")
    if status_code == 429:
        return EmailRateLimitError("Email provider rate limit reached")
    if status_code >= 500:
        return EmailProviderServerError("Email provider server error")
    return EmailDeliveryError("Email provider delivery failed")
