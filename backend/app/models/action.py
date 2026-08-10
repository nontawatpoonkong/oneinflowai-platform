"""Generic business fulfillment queue models."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class ActionExecutionMode(enum.StrEnum):
    MANUAL = "MANUAL"
    AUTOMATED = "AUTOMATED"


class ActionRequestStatus(enum.StrEnum):
    WAITING = "WAITING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ActionPriority(enum.StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ActionActorType(enum.StrEnum):
    AI = "AI"
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"


class ActionEventType(enum.StrEnum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def _enum(enum_type: type[enum.StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type, name=name, values_callable=lambda cls: [m.value for m in cls]
    )


class ActionDefinition(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "action_definitions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "key", name="uq_action_definition_workspace_key"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    execution_mode: Mapped[ActionExecutionMode] = mapped_column(
        _enum(ActionExecutionMode, "action_execution_mode"),
        default=ActionExecutionMode.MANUAL,
    )
    required_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    optional_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )


class ActionRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "action_requests"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_action_request_workspace_idempotency",
        ),
        Index("ix_action_requests_queue", "workspace_id", "status", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    action_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("action_definitions.id", ondelete="RESTRICT"),
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
    status: Mapped[ActionRequestStatus] = mapped_column(
        _enum(ActionRequestStatus, "action_request_status"),
        default=ActionRequestStatus.WAITING,
    )
    priority: Mapped[ActionPriority] = mapped_column(
        _enum(ActionPriority, "action_priority"), default=ActionPriority.NORMAL
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_type: Mapped[ActionActorType] = mapped_column(
        _enum(ActionActorType, "action_actor_type"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    assigned_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ActionEvent(UUIDMixin, Base):
    __tablename__ = "action_events"
    __table_args__ = (
        Index("ix_action_events_request_created", "action_request_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    action_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("action_requests.id", ondelete="RESTRICT"),
        index=True,
    )
    event_type: Mapped[ActionEventType] = mapped_column(
        _enum(ActionEventType, "action_event_type"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_type: Mapped[ActionActorType] = mapped_column(
        _enum(ActionActorType, "action_event_actor_type"), nullable=False
    )
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
