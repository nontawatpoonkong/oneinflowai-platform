"""Workspace-scoped AI tool proposals, execution audit, and bounded context."""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class AIToolClassification(enum.StrEnum):
    READ_ONLY = "READ_ONLY"
    MUTATING_REVERSIBLE = "MUTATING_REVERSIBLE"
    MUTATING_SENSITIVE = "MUTATING_SENSITIVE"


class AIToolActionStatus(enum.StrEnum):
    PROPOSED = "PROPOSED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AIToolAuditEventType(enum.StrEnum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


def _enum(enum_type: type[enum.StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        name=name,
        values_callable=lambda values: [item.value for item in values],
    )


class AIToolAction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_tool_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_ai_tool_action_conversation_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="RESTRICT",
            name="fk_ai_tool_action_customer_scope",
        ),
        UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_ai_tool_action_idempotency"
        ),
        UniqueConstraint("workspace_id", "id", name="uq_ai_tool_action_scope"),
        Index(
            "ix_ai_tool_action_conversation_status",
            "workspace_id",
            "conversation_id",
            "status",
            "created_at",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(16), nullable=False)
    classification: Mapped[AIToolClassification] = mapped_column(
        _enum(AIToolClassification, "ai_tool_classification"), nullable=False
    )
    status: Mapped[AIToolActionStatus] = mapped_column(
        _enum(AIToolActionStatus, "ai_tool_action_status"), nullable=False
    )
    validated_args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(64))
    confirmation_expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result_reference_type: Mapped[str | None] = mapped_column(String(32))
    result_reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)


class AIToolAuditEvent(UUIDMixin, Base):
    __tablename__ = "ai_tool_audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "action_id"],
            ["ai_tool_actions.workspace_id", "ai_tool_actions.id"],
            ondelete="CASCADE",
            name="fk_ai_tool_audit_action_scope",
        ),
        Index("ix_ai_tool_audit_action_created", "action_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[AIToolAuditEventType] = mapped_column(
        _enum(AIToolAuditEventType, "ai_tool_audit_event_type"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(16), nullable=False)
    result_status: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class AIConversationState(UUIDMixin, TimestampMixin, Base):
    """Small typed state only; never stores prompts or model reasoning."""

    __tablename__ = "ai_conversation_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_ai_conversation_state_scope",
        ),
        UniqueConstraint(
            "workspace_id", "conversation_id", name="uq_ai_conversation_state"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    selected_property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    selected_room_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    selected_rate_plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requested_check_in: Mapped[date | None] = mapped_column(Date)
    requested_check_out: Mapped[date | None] = mapped_column(Date)
    adults: Mapped[int | None]
    children: Mapped[int | None]
    quantity: Mapped[int | None]
    active_booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_availability_options: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
