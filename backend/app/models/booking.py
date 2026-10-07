"""Workspace-scoped booking holds and immutable lifecycle events."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class BookingStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    HELD = "HELD"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class BookingEventType(enum.StrEnum):
    BOOKING_CREATED = "BOOKING_CREATED"
    HOLD_CREATED = "HOLD_CREATED"
    HOLD_EXPIRED = "HOLD_EXPIRED"
    BOOKING_CANCELLED = "BOOKING_CANCELLED"
    PENDING_PAYMENT_STARTED = "PENDING_PAYMENT_STARTED"
    PAYMENT_LINKED = "PAYMENT_LINKED"
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED"
    PAYMENT_REQUIRES_REVIEW = "PAYMENT_REQUIRES_REVIEW"
    REPLACEMENT_PAYMENT_LINKED = "REPLACEMENT_PAYMENT_LINKED"
    PAYMENT_REVIEW_ACKNOWLEDGED = "PAYMENT_REVIEW_ACKNOWLEDGED"


def _enum(cls, name):
    return SAEnum(
        cls, name=name, values_callable=lambda values: [v.value for v in values]
    )


class Booking(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_bookings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id"],
            ["hotel_properties.workspace_id", "hotel_properties.id"],
            ondelete="RESTRICT",
            name="fk_hotel_booking_property_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="RESTRICT",
            name="fk_hotel_booking_customer_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="RESTRICT",
            name="fk_hotel_booking_conversation_scope",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_hotel_booking_scope"),
        UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_hotel_booking_property_scope"
        ),
        UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_hotel_booking_idempotency"
        ),
        Index("ix_hotel_bookings_workspace_status", "workspace_id", "status"),
        Index("ix_hotel_bookings_hold_expiry", "hold_expires_at"),
        CheckConstraint("check_out > check_in", name="ck_hotel_booking_stay"),
        CheckConstraint(
            "adults > 0 AND children >= 0", name="ck_hotel_booking_occupancy"
        ),
        CheckConstraint(
            "subtotal >= 0 AND total_amount >= 0", name="ck_hotel_booking_totals"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    guest_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[BookingStatus] = mapped_column(
        _enum(BookingStatus, "hotel_booking_status"), nullable=False
    )
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    adults: Mapped[int] = mapped_column(Integer, nullable=False)
    children: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    hold_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    property_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)


class BookingItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_booking_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "booking_id"],
            [
                "hotel_bookings.workspace_id",
                "hotel_bookings.property_id",
                "hotel_bookings.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_booking_item_booking_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id"],
            [
                "hotel_room_types.workspace_id",
                "hotel_room_types.property_id",
                "hotel_room_types.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_booking_item_room_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id", "rate_plan_id"],
            [
                "hotel_rate_plans.workspace_id",
                "hotel_rate_plans.property_id",
                "hotel_rate_plans.room_type_id",
                "hotel_rate_plans.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_booking_item_rate_scope",
        ),
        UniqueConstraint("booking_id", name="uq_hotel_booking_single_item"),
        CheckConstraint("quantity > 0", name="ck_hotel_booking_item_quantity"),
        CheckConstraint("subtotal >= 0", name="ck_hotel_booking_item_subtotal"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    room_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rate_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    nightly_rates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    occupancy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rate_policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    room_type_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    rate_plan_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)


class BookingEvent(UUIDMixin, Base):
    __tablename__ = "hotel_booking_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "booking_id"],
            ["hotel_bookings.workspace_id", "hotel_bookings.id"],
            ondelete="RESTRICT",
            name="fk_hotel_booking_event_scope",
        ),
        Index("ix_hotel_booking_events_booking_created", "booking_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[BookingEventType] = mapped_column(
        _enum(BookingEventType, "hotel_booking_event_type"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
