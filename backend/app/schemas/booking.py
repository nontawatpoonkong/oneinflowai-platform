"""Booking hold commands and immutable snapshot responses."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.booking import BookingEventType, BookingStatus
from app.models.payment import (
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentStatus,
)


class BookingHoldCreate(BaseModel):
    property_id: uuid.UUID
    room_type_id: uuid.UUID
    rate_plan_id: uuid.UUID
    check_in: date
    check_out: date
    adults: int = Field(gt=0)
    children: int = Field(default=0, ge=0)
    quantity: int = Field(default=1, gt=0)
    customer_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    guest_name: str | None = Field(default=None, min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=128)
    promotion_code: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def valid_hold(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        if not (self.customer_id or self.conversation_id or self.guest_name):
            raise ValueError("customer_id, conversation_id or guest_name is required")
        return self


class ManualBookingQuoteRequest(BaseModel):
    """Staff composer preview. Informational only; the Hold reprices."""

    property_id: uuid.UUID
    room_type_id: uuid.UUID
    rate_plan_id: uuid.UUID
    check_in: date
    check_out: date
    adults: int = Field(gt=0)
    children: int = Field(default=0, ge=0)
    quantity: int = Field(default=1, gt=0, le=50)
    customer_id: uuid.UUID | None = None
    promotion_code: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def valid_stay(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        if (self.check_out - self.check_in).days > 60:
            raise ValueError("stay cannot exceed 60 nights")
        return self


class BookingPaymentCreate(BaseModel):
    payment_destination_id: uuid.UUID


class BookingConfirmFromPayment(BaseModel):
    payment_id: uuid.UUID


class BookingPaymentReviewAcknowledge(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class BookingPaymentExceptionResponse(BaseModel):
    payment_id: uuid.UUID
    booking_id: uuid.UUID
    customer_id: uuid.UUID | None
    payment_status: PaymentStatus
    application_status: PaymentApplicationStatus | None
    reason: PaymentApplicationReason | None
    booking_status: BookingStatus
    payment_expected_amount: Decimal
    payment_verified_amount: Decimal | None
    payment_currency: str
    booking_total_amount: Decimal
    booking_currency: str
    payment_verified_at: datetime | None
    booking_hold_expires_at: datetime | None
    review_note: str | None
    reviewed_at: datetime | None


class BookingItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    room_type_id: uuid.UUID
    rate_plan_id: uuid.UUID
    quantity: int
    nightly_rates: list[dict[str, Any]]
    subtotal: Decimal
    occupancy_snapshot: dict[str, Any]
    rate_policy_snapshot: dict[str, Any]
    room_type_name_snapshot: str
    rate_plan_name_snapshot: str


class BookingEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: BookingEventType
    actor_type: str
    actor_user_id: uuid.UUID | None
    event_metadata: dict[str, Any]
    created_at: datetime


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    property_id: uuid.UUID
    customer_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    guest_name: str | None
    status: BookingStatus
    check_in: date
    check_out: date
    adults: int
    children: int
    currency: str
    subtotal: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    promotion_snapshot: dict[str, Any] | None
    hold_expires_at: datetime | None
    source: str
    property_name_snapshot: str
    item: BookingItemResponse
    events: list[BookingEventResponse]
