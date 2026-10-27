"""Customer-to-workspace payment and slip verification models."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class DestinationType(enum.StrEnum):
    BANK_ACCOUNT = "BANK_ACCOUNT"
    PROMPTPAY = "PROMPTPAY"


class PaymentStatus(enum.StrEnum):
    PENDING = "PENDING"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"


class PaymentApplicationStatus(enum.StrEnum):
    UNAPPLIED = "UNAPPLIED"
    APPLIED = "APPLIED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class PaymentApplicationReason(enum.StrEnum):
    BOOKING_EXPIRED = "BOOKING_EXPIRED"
    BOOKING_CANCELLED = "BOOKING_CANCELLED"
    BOOKING_ALREADY_CONFIRMED = "BOOKING_ALREADY_CONFIRMED"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    PAYMENT_ALREADY_APPLIED = "PAYMENT_ALREADY_APPLIED"
    BOOKING_LINK_CONFLICT = "BOOKING_LINK_CONFLICT"
    INVALID_BOOKING_STATE = "INVALID_BOOKING_STATE"
    PAYMENT_NOT_VERIFIED = "PAYMENT_NOT_VERIFIED"


class VerificationStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    VALID = "VALID"
    INVALID = "INVALID"
    ERROR = "ERROR"


def _enum(cls, name):
    return SAEnum(
        cls, name=name, values_callable=lambda values: [item.value for item in values]
    )


class PaymentDestination(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payment_destinations"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[DestinationType] = mapped_column(
        _enum(DestinationType, "payment_destination_type")
    )
    display_name: Mapped[str] = mapped_column(String(255))
    bank_code: Mapped[str | None] = mapped_column(String(32))
    bank_name: Mapped[str | None] = mapped_column(String(128))
    account_name: Mapped[str | None] = mapped_column(String(255))
    account_number_masked: Mapped[str | None] = mapped_column(String(64))
    promptpay_type: Mapped[str | None] = mapped_column(String(32))
    promptpay_identifier_protected: Mapped[str | None] = mapped_column(String(128))
    promptpay_identifier_last4: Mapped[str | None] = mapped_column(String(4))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )


class Payment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_payment_workspace_idempotency"
        ),
        Index(
            "uq_payment_booking_applied",
            "workspace_id",
            "booking_id",
            unique=True,
            postgresql_where=text("booking_applied_at IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["workspace_id", "booking_id"],
            ["hotel_bookings.workspace_id", "hotel_bookings.id"],
            ondelete="RESTRICT",
            name="fk_payment_booking_scope",
        ),
        Index("ix_payments_workspace_status", "workspace_id", "status"),
        Index(
            "ix_payments_application_review",
            "workspace_id",
            "booking_application_status",
        ),
        CheckConstraint(
            "booking_applied_at IS NULL OR booking_id IS NOT NULL",
            name="ck_payment_applied_has_booking",
        ),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    booking_applied_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    booking_application_status: Mapped[PaymentApplicationStatus | None] = mapped_column(
        _enum(PaymentApplicationStatus, "payment_application_status")
    )
    booking_application_reason: Mapped[PaymentApplicationReason | None] = mapped_column(
        _enum(PaymentApplicationReason, "payment_application_reason")
    )
    booking_review_note: Mapped[str | None] = mapped_column(String(1000))
    booking_reviewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    booking_reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("action_requests.id", ondelete="RESTRICT"),
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    payment_destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_destinations.id", ondelete="RESTRICT"),
        index=True,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        _enum(PaymentStatus, "payment_status"), default=PaymentStatus.PENDING
    )
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    verified_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="THB")
    reference: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class PaymentEvidence(UUIDMixin, Base):
    __tablename__ = "payment_evidence"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "content_hash", name="uq_payment_evidence_workspace_hash"
        ),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class PaymentVerification(UUIDMixin, Base):
    __tablename__ = "payment_verifications"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider",
            "transfer_reference",
            name="uq_payment_verification_transfer",
        ),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_evidence.id", ondelete="RESTRICT"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64))
    provider_reference: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[VerificationStatus] = mapped_column(
        _enum(VerificationStatus, "payment_verification_status")
    )
    reported_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    transfer_reference: Mapped[str | None] = mapped_column(String(128))
    transferred_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    receiver_match: Mapped[bool | None]
    amount_match: Mapped[bool | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
