"""Customer payment API schemas with safe destination details."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import (
    DestinationType,
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentStatus,
    VerificationStatus,
)


class PaymentDestinationCreate(BaseModel):
    type: DestinationType
    display_name: str = Field(min_length=1, max_length=255)
    bank_code: str | None = None
    bank_name: str | None = None
    account_name: str | None = None
    account_number_masked: str | None = None
    promptpay_type: str | None = None
    promptpay_identifier: str | None = Field(default=None, min_length=4, max_length=64)
    is_active: bool = True
    is_default: bool = False


class PaymentDestinationUpdate(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class PaymentDestinationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: DestinationType
    display_name: str
    bank_code: str | None
    bank_name: str | None
    account_name: str | None
    account_number_masked: str | None
    promptpay_type: str | None
    promptpay_identifier_last4: str | None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


class PaymentCreate(BaseModel):
    payment_destination_id: uuid.UUID
    expected_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="THB", pattern=r"^[A-Z]{3}$")
    action_request_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=128)
    expires_at: datetime | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    booking_id: uuid.UUID | None
    booking_applied_at: datetime | None
    booking_application_status: PaymentApplicationStatus | None
    booking_application_reason: PaymentApplicationReason | None
    booking_review_note: str | None
    booking_reviewed_at: datetime | None
    action_request_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    payment_destination_id: uuid.UUID
    status: PaymentStatus
    expected_amount: Decimal
    verified_amount: Decimal | None
    currency: str
    reference: str | None
    paid_at: datetime | None
    verified_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PaymentEvidenceResponse(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    mime_type: str
    file_size: int
    content_hash: str
    created_at: datetime


class PaymentVerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    payment_id: uuid.UUID
    evidence_id: uuid.UUID
    provider: str
    provider_reference: str | None
    status: VerificationStatus
    reported_amount: Decimal | None
    currency: str | None
    transfer_reference: str | None
    transferred_at: datetime | None
    receiver_match: bool | None
    amount_match: bool | None
    error_code: str | None
    verified_at: datetime | None
    created_at: datetime
