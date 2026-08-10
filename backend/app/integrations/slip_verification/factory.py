from app.core.config import Settings, get_settings
from app.core.exceptions import PaymentVerificationProviderError
from app.integrations.slip_verification.development import (
    DevelopmentSlipVerificationProvider,
)


def create_slip_verification_provider(settings: Settings | None = None):
    configured = settings or get_settings()
    if configured.SLIP_VERIFICATION_PROVIDER.strip().lower() == "development":
        return DevelopmentSlipVerificationProvider()
    raise PaymentVerificationProviderError(
        "Slip verification provider is not configured"
    )
