"""Typed input and result contracts for the initial trusted AI tools."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchAvailabilityInput(StrictContract):
    property_name: str | None = Field(default=None, min_length=1, max_length=255)
    check_in: date
    check_out: date
    adults: int = Field(gt=0)
    children: int = Field(default=0, ge=0)
    room_type_name: str | None = Field(default=None, min_length=1, max_length=255)
    rate_plan_name: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def valid_stay(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class RoomCatalogFactsInput(StrictContract):
    property_name: str | None = Field(default=None, min_length=1, max_length=255)
    room_type_name: str = Field(min_length=1, max_length=255)


class CreateBookingHoldInput(StrictContract):
    option_index: int = Field(default=1, ge=1, le=10)
    check_in: date | None = None
    check_out: date | None = None
    adults: int | None = Field(default=None, gt=0)
    children: int | None = Field(default=None, ge=0)
    quantity: int = Field(default=1, gt=0, le=10)
    promotion_code: str | None = Field(default=None, min_length=1, max_length=32)


class ValidatePromotionCodeInput(StrictContract):
    code: str = Field(min_length=1, max_length=32)
    option_index: int = Field(default=1, ge=1, le=10)
    quantity: int = Field(default=1, gt=0, le=10)


class RequestBookingPaymentInput(StrictContract):
    destination_name: str | None = Field(default=None, min_length=1, max_length=255)


class EmptyToolInput(StrictContract):
    pass


class HandoffInput(StrictContract):
    reason: str = Field(default="customer_request", min_length=1, max_length=64)


class AvailabilityOption(StrictContract):
    option_index: int
    property_name: str
    room_type_name: str
    rate_plan_name: str
    check_in: date
    check_out: date
    currency: str
    subtotal: Decimal
    available_units: int
    refundable: bool


class AvailabilityResult(StrictContract):
    options: list[AvailabilityOption]


class BookingHoldResult(StrictContract):
    booking_status: str
    property_name: str
    room_type_name: str
    rate_plan_name: str
    check_in: date
    check_out: date
    currency: str
    subtotal: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    promotion_code: str | None
    hold_expires_at: datetime | None


class BookingStatusResult(StrictContract):
    booking_status: str
    property_name: str
    room_type_name: str
    rate_plan_name: str
    check_in: date
    check_out: date
    currency: str
    subtotal: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    promotion_code: str | None
    hold_expires_at: datetime | None
    payment_status: str | None
    payment_application_status: str | None
    payment_requires_review: bool


class PaymentRequestResult(StrictContract):
    payment_status: str
    booking_status: str
    currency: str
    expected_amount: Decimal
    destination_display_name: str
    destination_type: str
    destination_account_masked: str | None
    destination_promptpay_last4: str | None
    expires_at: datetime | None


class PaymentStatusResult(StrictContract):
    payment_status: str
    booking_status: str | None
    application_status: str | None
    requires_review: bool
    review_reason: str | None
    currency: str
    expected_amount: Decimal
    verified_amount: Decimal | None


class HandoffResult(StrictContract):
    conversation_mode: str
    handoff_reason: str


class PromotionValidationToolResult(StrictContract):
    valid: bool
    reason_code: str | None
    code: str | None
    promotion_name: str | None
    discount_amount: Decimal
    subtotal: Decimal
    final_total: Decimal
    currency: str


ToolResult = dict[str, Any]
