from app.core.config import Settings, get_settings
from app.core.exceptions import PaymentVerificationProviderError
from app.integrations.slip_verification.development import (
    DevelopmentSlipVerificationProvider,
)
from app.integrations.slip_verification.easyslip import EasySlipVerificationProvider


def create_slip_verification_provider(settings: Settings | None = None):
    configured = settings or get_settings()
    if configured.SLIP_VERIFICATION_PROVIDER.strip().lower() == "development":
        return DevelopmentSlipVerificationProvider()
    if configured.SLIP_VERIFICATION_PROVIDER.strip().lower() == "easyslip_v2":
        if not configured.EASYSLIP_API_KEY:
            raise PaymentVerificationProviderError(
                "Slip verification provider is not configured"
            )
        return EasySlipVerificationProvider(
            configured.EASYSLIP_API_KEY,
            configured.SLIP_VERIFICATION_TIMEOUT_SECONDS,
        )
    raise PaymentVerificationProviderError(
        "Slip verification provider is not configured"
    )
