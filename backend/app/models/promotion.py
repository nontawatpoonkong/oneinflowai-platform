"""Workspace-scoped promotion, attribution, and redemption models."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


def _enum(cls, name):
    return SAEnum(
        cls, name=name, values_callable=lambda values: [value.value for value in values]
    )


class PromotionCampaignStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class PromotionDiscountType(enum.StrEnum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class PromotionCodeStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    EXHAUSTED = "EXHAUSTED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class PromotionSource(enum.StrEnum):
    DIRECT = "DIRECT"
    WEBCHAT = "WEBCHAT"
    LINE = "LINE"
    FACEBOOK = "FACEBOOK"
    INSTAGRAM = "INSTAGRAM"
    PARTNER = "PARTNER"
    MANUAL = "MANUAL"
    OTHER = "OTHER"


class PromotionManagementOrigin(enum.StrEnum):
    """Who authored a Workspace-owned campaign; never who funds the discount."""

    WORKSPACE = "WORKSPACE"
    PLATFORM = "PLATFORM"


class PromotionRedemptionStatus(enum.StrEnum):
    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"


class PromotionCampaign(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "promotion_campaigns"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_promotion_campaign_scope"),
        Index(
            "ix_promotion_campaign_workspace_status",
            "workspace_id",
            "status",
            "updated_at",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_promotion_campaign_validity",
        ),
        CheckConstraint(
            "management_origin IN ('WORKSPACE','PLATFORM')",
            name="ck_promotion_campaign_origin",
        ),
        Index(
            "ix_promotion_campaign_lifecycle_expiry",
            "status",
            "valid_until",
        ),
        Index(
            "ix_promotion_campaign_lifecycle_start",
            "status",
            "valid_from",
            postgresql_where="started_at IS NULL",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[PromotionCampaignStatus] = mapped_column(
        _enum(PromotionCampaignStatus, "promotion_campaign_status"), nullable=False
    )
    valid_from: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    management_origin: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PromotionManagementOrigin.WORKSPACE.value,
        server_default=PromotionManagementOrigin.WORKSPACE.value,
    )
    # Set once when an ACTIVE campaign's validity window has actually begun.
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Promotion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "promotions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["promotion_campaigns.workspace_id", "promotion_campaigns.id"],
            ondelete="RESTRICT",
            name="fk_promotion_campaign_scope",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_promotion_scope"),
        Index("ix_promotion_workspace_campaign", "workspace_id", "campaign_id"),
        CheckConstraint("discount_value > 0", name="ck_promotion_discount_positive"),
        CheckConstraint(
            "discount_type <> 'PERCENTAGE' OR discount_value <= 100",
            name="ck_promotion_percentage_range",
        ),
        CheckConstraint(
            "max_discount_amount IS NULL OR max_discount_amount >= 0",
            name="ck_promotion_max_discount",
        ),
        CheckConstraint(
            "minimum_subtotal IS NULL OR minimum_subtotal >= 0",
            name="ck_promotion_minimum_subtotal",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_promotion_validity",
        ),
        CheckConstraint(
            "stay_date_end IS NULL OR stay_date_start IS NULL OR "
            "stay_date_end >= stay_date_start",
            name="ck_promotion_stay_dates",
        ),
        CheckConstraint(
            "total_usage_limit IS NULL OR total_usage_limit > 0",
            name="ck_promotion_total_usage_limit",
        ),
        CheckConstraint(
            "per_customer_limit IS NULL OR per_customer_limit > 0",
            name="ck_promotion_customer_limit",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    discount_type: Mapped[PromotionDiscountType] = mapped_column(
        _enum(PromotionDiscountType, "promotion_discount_type"), nullable=False
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    max_discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    minimum_subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    valid_from: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    stay_date_start: Mapped[date | None] = mapped_column(Date)
    stay_date_end: Mapped[date | None] = mapped_column(Date)
    total_usage_limit: Mapped[int | None] = mapped_column(Integer)
    per_customer_limit: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PromotionCode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "promotion_codes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="RESTRICT",
            name="fk_promotion_code_promotion_scope",
        ),
        UniqueConstraint(
            "workspace_id", "normalized_code", name="uq_promotion_code_workspace"
        ),
        UniqueConstraint("workspace_id", "id", name="uq_promotion_code_scope"),
        CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0",
            name="ck_promotion_code_usage_limit",
        ),
        Index("ix_promotion_code_lookup", "workspace_id", "normalized_code"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    promotion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[PromotionCodeStatus] = mapped_column(
        _enum(PromotionCodeStatus, "promotion_code_status"), nullable=False
    )
    usage_limit: Mapped[int | None] = mapped_column(Integer)


class PromotionProperty(Base):
    __tablename__ = "promotion_properties"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "property_id"],
            ["hotel_properties.workspace_id", "hotel_properties.id"],
            ondelete="RESTRICT",
        ),
    )


class PromotionRoomType(Base):
    __tablename__ = "promotion_room_types"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "room_type_id"],
            ["hotel_room_types.workspace_id", "hotel_room_types.id"],
            ondelete="RESTRICT",
        ),
    )


class PromotionRatePlan(Base):
    __tablename__ = "promotion_rate_plans"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    rate_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "rate_plan_id"],
            ["hotel_rate_plans.workspace_id", "hotel_rate_plans.id"],
            ondelete="RESTRICT",
        ),
    )


class PromotionSourceEligibility(Base):
    __tablename__ = "promotion_sources"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    source: Mapped[PromotionSource] = mapped_column(
        _enum(PromotionSource, "promotion_source"), primary_key=True
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="CASCADE",
        ),
    )


class BookingAttribution(UUIDMixin, Base):
    __tablename__ = "booking_attributions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "booking_id"],
            ["hotel_bookings.workspace_id", "hotel_bookings.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["promotion_campaigns.workspace_id", "promotion_campaigns.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "promotion_code_id"],
            ["promotion_codes.workspace_id", "promotion_codes.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("booking_id", name="uq_booking_attribution_booking"),
        Index("ix_booking_attribution_workspace_source", "workspace_id", "source"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source: Mapped[PromotionSource] = mapped_column(
        _enum(PromotionSource, "booking_attribution_source"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    promotion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    promotion_code_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    partner_identifier: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class PromotionRedemption(UUIDMixin, Base):
    __tablename__ = "promotion_redemptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "booking_id"],
            ["hotel_bookings.workspace_id", "hotel_bookings.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "promotion_code_id"],
            ["promotion_codes.workspace_id", "promotion_codes.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("booking_id", name="uq_promotion_redemption_booking"),
        CheckConstraint("discount_amount >= 0", name="ck_redemption_discount"),
        Index(
            "ix_promotion_redemption_usage",
            "workspace_id",
            "promotion_id",
            "status",
            "redeemed_at",
        ),
        Index(
            "ix_promotion_redemption_customer",
            "workspace_id",
            "promotion_id",
            "customer_id",
            "status",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    promotion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    promotion_code_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PromotionRedemptionStatus] = mapped_column(
        _enum(PromotionRedemptionStatus, "promotion_redemption_status"), nullable=False
    )
    reserved_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
