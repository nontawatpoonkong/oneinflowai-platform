"""Email provider contract."""

from abc import ABC, abstractmethod


class EmailDeliveryError(Exception):
    """A provider-safe email delivery failure."""


class EmailConfigurationError(EmailDeliveryError):
    """Email delivery is not configured correctly."""


class EmailAuthenticationError(EmailDeliveryError):
    """The email provider rejected its credentials or permissions."""


class EmailRateLimitError(EmailDeliveryError):
    """The email provider rate limit was reached."""


class EmailNetworkError(EmailDeliveryError):
    """The email provider could not be reached."""


class EmailProviderServerError(EmailDeliveryError):
    """The email provider reported a server-side failure."""


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

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_seconds: int,
    ) -> None:
        """Send a password-reset code."""
        raise NotImplementedError
