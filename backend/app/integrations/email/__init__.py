"""Provider-neutral email delivery infrastructure."""

from app.integrations.email.base import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailDeliveryError,
    EmailNetworkError,
    EmailProvider,
    EmailProviderServerError,
    EmailRateLimitError,
)
from app.integrations.email.factory import create_email_provider, get_email_provider

__all__ = [
    "EmailAuthenticationError",
    "EmailConfigurationError",
    "EmailDeliveryError",
    "EmailNetworkError",
    "EmailProvider",
    "EmailProviderServerError",
    "EmailRateLimitError",
    "create_email_provider",
    "get_email_provider",
]
