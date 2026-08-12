"""Deterministic non-authoritative development slip verifier."""

from app.integrations.slip_verification.base import (
    SlipVerificationRequest,
    SlipVerificationResult,
)


class DevelopmentSlipVerificationProvider:
    name = "development"

    async def verify(self, evidence: SlipVerificationRequest) -> SlipVerificationResult:
        return SlipVerificationResult(
            provider=self.name,
            provider_reference=f"dev-{evidence.content_hash[:16]}",
            is_valid=True,
            amount=evidence.expected_amount,
            currency=evidence.currency,
            transfer_reference=f"dev-transfer-{evidence.content_hash[:24]}",
            transferred_at=None,
            receiver_name=evidence.destination_account_name,
            receiver_account_masked=(
                evidence.destination_account_masked
                or evidence.destination_promptpay_last4
            ),
            receiver_bank=(
                evidence.destination_bank_code or evidence.destination_bank_name
            ),
            duplicate_reference_signal=False,
            raw_status_code="DEVELOPMENT_FIXTURE",
        )
