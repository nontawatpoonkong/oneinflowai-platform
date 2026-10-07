"""Typed Guest CRM requests and bounded Customer 360 responses."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.channels import ChannelType
from app.models.booking import BookingStatus
from app.models.conversation import ConversationMode, ConversationStatus
from app.models.crm import CustomerPreferenceKey, CustomerPreferenceSource
from app.models.customer import CustomerStatus
from app.models.payment import (
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentStatus,
)


class CRMCustomer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    full_name: str | None
    phone: str | None
    email: str | None
    avatar_url: str | None
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime


class CustomerIdentitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: ChannelType
    external_username: str | None
    created_at: datetime


class CustomerTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())


class CustomerTagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    normalized_name: str
    created_at: datetime


class CustomerPreferenceWrite(BaseModel):
    key: CustomerPreferenceKey
    value: str = Field(min_length=1, max_length=500)
    source: CustomerPreferenceSource = CustomerPreferenceSource.STAFF_CONFIRMED

    @field_validator("value")
    @classmethod
    def clean_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Preference value cannot be empty")
        return value


class CustomerPreferenceUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=500)
    source: CustomerPreferenceSource = CustomerPreferenceSource.STAFF_CONFIRMED

    @field_validator("value")
    @classmethod
    def clean_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Preference value cannot be empty")
        return value


class CustomerPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: CustomerPreferenceKey
    value: str
    source: CustomerPreferenceSource
    confirmed_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CustomerNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Note cannot be empty")
        return value


class CustomerNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class ConversationSummary(BaseModel):
    id: uuid.UUID
    channel: ChannelType
    status: ConversationStatus
    ai_mode: ConversationMode
    assigned_user_id: uuid.UUID | None
    last_message_at: datetime | None
    needs_attention: bool
    unread: bool
    preview: str | None


class BookingSummary(BaseModel):
    id: uuid.UUID
    property_name: str
    room_type_name: str | None
    check_in: date
    check_out: date
    status: BookingStatus
    total_amount: Decimal
    currency: str
    created_at: datetime
    confirmed_at: datetime | None


class PaymentSummary(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID | None
    expected_amount: Decimal
    verified_amount: Decimal | None
    currency: str
    status: PaymentStatus
    application_status: PaymentApplicationStatus | None
    application_reason: PaymentApplicationReason | None
    created_at: datetime
    verified_at: datetime | None
    booking_applied_at: datetime | None


class PaymentExceptionSummary(BaseModel):
    payment_id: uuid.UUID
    booking_id: uuid.UUID | None
    reason: PaymentApplicationReason | None
    verified_amount: Decimal | None
    currency: str
    verified_at: datetime | None


class StaySummary(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    property_name: str
    room_codes: list[str]
    planned_check_in_date: date
    planned_check_out_date: date
    actual_check_in_at: datetime | None
    actual_check_out_at: datetime | None
    status: str


class RepeatGuestSummary(BaseModel):
    repeat_guest: bool
    confirmed_bookings: int
    cancelled_bookings: int
    latest_booking_date: date | None


class Customer360Response(BaseModel):
    customer: CRMCustomer
    identities: list[CustomerIdentitySummary]
    tags: list[CustomerTagResponse]
    preferences: list[CustomerPreferenceResponse]
    notes: list[CustomerNoteResponse]
    conversations: list[ConversationSummary]
    bookings: list[BookingSummary]
    payments: list[PaymentSummary]
    payment_exceptions: list[PaymentExceptionSummary]
    stays: list[StaySummary]
    repeat_guest_summary: RepeatGuestSummary


class CustomerListItem(BaseModel):
    customer: CRMCustomer
    tags: list[CustomerTagResponse]
    booking_count: int
    confirmed_bookings: int
    repeat_guest: bool
    latest_booking_status: BookingStatus | None
    has_payment_exception: bool
    last_conversation_at: datetime | None
    needs_attention: bool


class CustomerListResponse(BaseModel):
    items: list[CustomerListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class TimelineEvent(BaseModel):
    id: str
    type: str
    occurred_at: datetime
    entity_type: str
    entity_id: uuid.UUID
    summary: str
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    items: list[TimelineEvent]
    total: int
    page: int
    page_size: int
    total_pages: int
