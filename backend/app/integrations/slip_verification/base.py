"""Provider-neutral authoritative slip verification contracts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SlipVerificationRequest:
    content_hash: str
    expected_amount: Decimal
    currency: str
    destination_hint: str


@dataclass(frozen=True, slots=True)
class SlipVerificationResult:
    provider: str
    provider_reference: str | None
    is_valid: bool
    amount: Decimal | None
    currency: str | None
    transfer_reference: str | None
    transferred_at: datetime | None
    receiver_match: bool | None
    raw_status_code: str | None = None


class SlipVerificationProvider(Protocol):
    name: str

    async def verify(
        self, evidence: SlipVerificationRequest
    ) -> SlipVerificationResult: ...
