"""Configured email provider selection."""

from app.core.config import Settings, get_settings
from app.integrations.email.base import EmailProvider
from app.integrations.email.development import DevelopmentEmailProvider


def create_email_provider(settings: Settings | None = None) -> EmailProvider:
    resolved = settings or get_settings()
    provider = resolved.EMAIL_PROVIDER.strip().lower()
    if provider == "development":
        return DevelopmentEmailProvider()
    raise ValueError(f"Unsupported email provider: {resolved.EMAIL_PROVIDER!r}")
