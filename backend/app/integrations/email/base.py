"""Email provider contract."""

from abc import ABC, abstractmethod


class EmailDeliveryError(Exception):
    """A provider-safe email delivery failure."""


class EmailProvider(ABC):
    @abstractmethod
    async def send_verification_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_seconds: int,
    ) -> None:
        """Send an email verification code."""
        raise NotImplementedError
