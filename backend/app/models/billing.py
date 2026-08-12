"""SaaS billing models, deliberately separate from customer payments."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class BillingInterval(enum.StrEnum):
    MONTH = "MONTH"
    YEAR = "YEAR"


class EntitlementKind(enum.StrEnum):
    BOOLEAN = "BOOLEAN"
    LIMITED = "LIMITED"
    UNLIMITED = "UNLIMITED"


class SubscriptionStatus(enum.StrEnum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


class SaaSPlan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saas_plans"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    billing_interval: Mapped[BillingInterval] = mapped_column(
        SAEnum(BillingInterval, name="billing_interval"), nullable=False
    )
    price_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(3))
    pricing_note: Mapped[str | None] = mapped_column(String(255))


class PlanEntitlement(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "plan_entitlements"
    __table_args__ = (
        UniqueConstraint("plan_id", "key", name="uq_plan_entitlement_key"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saas_plans.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    kind: Mapped[EntitlementKind] = mapped_column(
        SAEnum(EntitlementKind, name="entitlement_kind"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    limit_value: Mapped[int | None] = mapped_column(BigInteger)
    overage_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )


class WorkspaceSubscription(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspace_subscriptions"
    __table_args__ = (
        Index("ix_workspace_subscription_lookup", "workspace_id", "status"),
        Index(
            "uq_workspace_effective_subscription",
            "workspace_id",
            unique=True,
            postgresql_where=text("status IN ('TRIALING', 'ACTIVE', 'PAST_DUE')"),
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saas_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status"), nullable=False
    )
    billing_interval: Mapped[BillingInterval] = mapped_column(
        SAEnum(BillingInterval, name="billing_interval"), nullable=False
    )
    current_period_start: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    trial_end: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    canceled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    provider: Mapped[str | None] = mapped_column(String(64))
    provider_customer_ref: Mapped[str | None] = mapped_column(String(255))
    provider_subscription_ref: Mapped[str | None] = mapped_column(String(255))


class SaaSUsageRecord(UUIDMixin, Base):
    __tablename__ = "saas_usage_records"
    __table_args__ = (
        Index("ix_saas_usage_period", "workspace_id", "meter", "occurred_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    meter: Mapped[str] = mapped_column(String(96), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
