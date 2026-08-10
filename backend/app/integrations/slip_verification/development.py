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
            receiver_match=True,
            raw_status_code="DEVELOPMENT_FIXTURE",
        )
