"""Provider-neutral authoritative slip verification contracts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


class SlipVerificationErrorCode:
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class SlipVerificationProviderError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SlipVerificationRequest:
    content_hash: str
    content: bytes
    mime_type: str
    expected_amount: Decimal
    currency: str
    destination_bank_code: str | None
    destination_bank_name: str | None
    destination_account_name: str | None
    destination_account_masked: str | None
    destination_promptpay_last4: str | None


@dataclass(frozen=True, slots=True)
class SlipVerificationResult:
    provider: str
    provider_reference: str | None
    is_valid: bool
    amount: Decimal | None
    currency: str | None
    transfer_reference: str | None
    transferred_at: datetime | None
    receiver_name: str | None
    receiver_account_masked: str | None
    receiver_bank: str | None
    duplicate_reference_signal: bool | None
    raw_status_code: str | None = None


class SlipVerificationProvider(Protocol):
    name: str

    async def verify(
        self, evidence: SlipVerificationRequest
    ) -> SlipVerificationResult: ...
