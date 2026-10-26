"""Immutable workspace audit history and privacy-bounded product telemetry."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import UUIDMixin


class AuditActorType(enum.StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    AI = "AI"
    AUTOMATION = "AUTOMATION"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"


class AuditResult(enum.StrEnum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILED = "FAILED"


class AuditArea(enum.StrEnum):
    WORKSPACE = "WORKSPACE"
    TEAM = "TEAM"
    CONVERSATIONS = "CONVERSATIONS"
    GUESTS = "GUESTS"
    BOOKINGS = "BOOKINGS"
    PAYMENTS = "PAYMENTS"
    ROOMS = "ROOMS"
    STAYS = "STAYS"
    HOUSEKEEPING = "HOUSEKEEPING"
    KNOWLEDGE = "KNOWLEDGE"
    AUTOMATIONS = "AUTOMATIONS"
    PMS = "PMS"
    ANALYTICS = "ANALYTICS"
    BILLING = "BILLING"
    SETTINGS = "SETTINGS"
    AI_ACTIONS = "AI_ACTIONS"
    PROMOTIONS = "PROMOTIONS"


class ProductUsageEventName(enum.StrEnum):
    PAGE_VIEW = "PAGE_VIEW"


class ProductFeature(enum.StrEnum):
    HOME = "HOME"
    CONVERSATIONS = "CONVERSATIONS"
    GUESTS = "GUESTS"
    BOOKINGS = "BOOKINGS"
    PAYMENTS = "PAYMENTS"
    AVAILABILITY = "AVAILABILITY"
    ROOMS = "ROOMS"
    STAYS = "STAYS"
    HOUSEKEEPING = "HOUSEKEEPING"
    AUTOMATIONS = "AUTOMATIONS"
    PMS = "PMS"
    ANALYTICS = "ANALYTICS"
    KNOWLEDGE = "KNOWLEDGE"
    TEAM = "TEAM"
    SETTINGS = "SETTINGS"
    PROMOTIONS = "PROMOTIONS"


class WorkspaceAuditEvent(UUIDMixin, Base):
    """Append-only cross-domain accountability record.

    Domain event tables remain the authoritative state-transition histories.
    This row is deliberately small and safe for long-term operator inspection.
    """

    __tablename__ = "workspace_audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('USER','SYSTEM','AI','AUTOMATION','PLATFORM_ADMIN')",
            name="ck_workspace_audit_actor_type",
        ),
        CheckConstraint(
            "result IN ('SUCCESS','DENIED','FAILED')",
            name="ck_workspace_audit_result",
        ),
        Index(
            "ix_workspace_audit_workspace_occurred",
            "workspace_id",
            "occurred_at",
            "id",
        ),
        Index("ix_workspace_audit_actor_occurred", "actor_user_id", "occurred_at"),
        Index("ix_workspace_audit_action_occurred", "action", "occurred_at"),
        Index("ix_workspace_audit_area_occurred", "area", "occurred_at"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    action: Mapped[str] = mapped_column(String(96), nullable=False)
    area: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    route: Mapped[str | None] = mapped_column(String(255))
    request_method: Mapped[str | None] = mapped_column(String(8))
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ProductUsageEvent(UUIDMixin, Base):
    """First-party, non-invasive product interaction telemetry."""

    __tablename__ = "product_usage_events"
    __table_args__ = (
        CheckConstraint(
            "event_name IN ('PAGE_VIEW')", name="ck_product_usage_event_name"
        ),
        UniqueConstraint(
            "workspace_id",
            "user_id",
            "event_name",
            "navigation_id",
            name="uq_product_usage_navigation",
        ),
        Index(
            "ix_product_usage_workspace_occurred",
            "workspace_id",
            "occurred_at",
            "id",
        ),
        Index(
            "ix_product_usage_workspace_feature",
            "workspace_id",
            "feature",
            "occurred_at",
        ),
        Index("ix_product_usage_user_occurred", "user_id", "occurred_at"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    session_id: Mapped[str | None] = mapped_column(String(128))
    navigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_name: Mapped[str] = mapped_column(String(32), nullable=False)
    page_path: Mapped[str] = mapped_column(String(255), nullable=False)
    feature: Mapped[str | None] = mapped_column(String(32))
    safe_properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


def _reject_audit_mutation(_mapper, _connection, _target) -> None:
    raise RuntimeError("workspace_audit_events is append-only")


event.listen(WorkspaceAuditEvent, "before_update", _reject_audit_mutation)
event.listen(WorkspaceAuditEvent, "before_delete", _reject_audit_mutation)
