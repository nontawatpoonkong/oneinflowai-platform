"""Configured email provider selection."""

from email_validator import EmailNotValidError, validate_email

from app.core.config import Settings, get_settings
from app.integrations.email.base import EmailConfigurationError, EmailProvider
from app.integrations.email.development import DevelopmentEmailProvider
from app.integrations.email.resend import ResendEmailProvider


def create_email_provider(settings: Settings | None = None) -> EmailProvider:
    resolved = settings or get_settings()
    provider = resolved.EMAIL_PROVIDER.strip().lower()
    if provider == "development":
        return DevelopmentEmailProvider()
    if provider == "resend":
        api_key = (resolved.RESEND_API_KEY or "").strip()
        if not api_key:
            raise EmailConfigurationError("RESEND_API_KEY is required")

        from_address = resolved.EMAIL_FROM_ADDRESS.strip()
        try:
            validated = validate_email(from_address, check_deliverability=False)
        except EmailNotValidError:
            raise EmailConfigurationError(
                "A valid EMAIL_FROM_ADDRESS is required"
            ) from None

        from_name = resolved.EMAIL_FROM_NAME.strip()
        if not from_name or "\r" in from_name or "\n" in from_name:
            raise EmailConfigurationError("A valid EMAIL_FROM_NAME is required")

        return ResendEmailProvider(
            api_key=api_key,
            from_address=validated.normalized,
            from_name=from_name,
        )
    raise EmailConfigurationError("Unsupported EMAIL_PROVIDER configuration")


def get_email_provider(settings: Settings | None = None) -> EmailProvider:
    """Compatibility alias for retrieving the configured provider."""
    return create_email_provider(settings)
