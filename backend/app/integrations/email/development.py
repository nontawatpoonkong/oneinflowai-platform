"""Safe local email provider that never logs message contents or OTPs."""

from app.core.logging import get_logger
from app.integrations.email.base import EmailProvider
from app.integrations.email.templates import (
    build_password_reset_email,
    build_verification_email,
)

logger = get_logger(__name__)


class DevelopmentEmailProvider(EmailProvider):
    async def send_verification_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_seconds: int,
    ) -> None:
        """Acknowledge delivery locally without exposing sensitive content."""
        build_verification_email(otp=otp, expires_in_seconds=expires_in_seconds)
        logger.info(
            "verification_email_suppressed",
            extra={"event": "verification_email_suppressed"},
        )

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_seconds: int,
    ) -> None:
        build_password_reset_email(otp=otp, expires_in_seconds=expires_in_seconds)
        logger.info(
            "password_reset_email_suppressed",
            extra={"event": "password_reset_email_suppressed"},
        )
