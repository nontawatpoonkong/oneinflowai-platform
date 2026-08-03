"""Provider-neutral email delivery infrastructure."""

from app.integrations.email.base import EmailDeliveryError, EmailProvider
from app.integrations.email.factory import create_email_provider

__all__ = ["EmailDeliveryError", "EmailProvider", "create_email_provider"]
