"""SaaS billing models, deliberately separate from customer payments."""

import enum
import uuid
from datetime import UTC, datetime

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
    PENDING_ACTIVATION = "PENDING_ACTIVATION"
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


class BillingAccountStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class BillingAccount(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "billing_accounts"
    __table_args__ = (
        UniqueConstraint("owner_user_id", name="uq_billing_account_owner"),
        Index("ix_billing_accounts_owner_user_id", "owner_user_id"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[BillingAccountStatus] = mapped_column(
        SAEnum(BillingAccountStatus, name="billing_account_status"),
        nullable=False,
        default=BillingAccountStatus.ACTIVE,
        server_default=BillingAccountStatus.ACTIVE.value,
    )


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
            "ix_workspace_subscriptions_billing_account",
            "billing_account_id",
            "status",
        ),
        Index(
            "uq_workspace_effective_subscription",
            "workspace_id",
            unique=True,
            postgresql_where=text("status IN ('TRIALING', 'ACTIVE', 'PAST_DUE')"),
        ),
    )

    billing_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("billing_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
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
    workspace_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default="1"
    )


class SubscriptionWorkspaceAllocation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "subscription_workspace_allocations"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "workspace_id", name="uq_subscription_workspace"
        ),
        UniqueConstraint("workspace_id", name="uq_workspace_billing_allocation"),
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    allocated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class BillingAuditEvent(UUIDMixin, Base):
    __tablename__ = "billing_audit_events"
    __table_args__ = (
        Index("ix_billing_audit_account_created", "billing_account_id", "created_at"),
    )

    billing_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("billing_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )


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
