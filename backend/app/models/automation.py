"""Durable, workspace-scoped hotel automation records."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class OutboxState(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class AutomationActionType(enum.StrEnum):
    INTERNAL_NOTIFICATION = "internal.notification"
    CUSTOMER_MESSAGE = "customer.message"


class AutomationScheduleMode(enum.StrEnum):
    IMMEDIATE = "IMMEDIATE"
    DELAY_AFTER_EVENT = "DELAY_AFTER_EVENT"
    BEFORE_DATE_FIELD = "BEFORE_DATE_FIELD"
    AFTER_DATE_FIELD = "AFTER_DATE_FIELD"


class AutomationExecutionStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AutomationWorkerState(enum.StrEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class DomainEventOutbox(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "automation_domain_events"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "deduplication_key", name="uq_automation_event_dedupe"
        ),
        UniqueConstraint("workspace_id", "id", name="uq_automation_event_scope"),
        CheckConstraint("event_version > 0", name="ck_automation_event_version"),
        CheckConstraint("attempt_count >= 0", name="ck_automation_event_attempts"),
        Index(
            "ix_automation_events_claim",
            "state",
            "available_at",
            "created_at",
        ),
        Index("ix_automation_events_workspace_type", "workspace_id", "event_type"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(128))
    event_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    available_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    state: Mapped[str] = mapped_column(
        String(16), default=OutboxState.PENDING.value, server_default="PENDING"
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deduplication_key: Mapped[str] = mapped_column(String(255))


class AutomationDefinition(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "automation_definitions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_automation_definition_scope"),
        CheckConstraint("trigger_version > 0", name="ck_automation_trigger_version"),
        Index(
            "ix_automation_definitions_trigger", "workspace_id", "trigger_event_type"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    trigger_event_type: Mapped[str] = mapped_column(String(128))
    trigger_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    action_type: Mapped[str] = mapped_column(String(64))
    action_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    schedule_mode: Mapped[str] = mapped_column(
        String(32), default=AutomationScheduleMode.IMMEDIATE.value
    )
    schedule_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class AutomationExecution(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "automation_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "automation_id"],
            ["automation_definitions.workspace_id", "automation_definitions.id"],
            name="fk_automation_execution_definition_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "event_id"],
            ["automation_domain_events.workspace_id", "automation_domain_events.id"],
            name="fk_automation_execution_event_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "automation_id", "event_id", name="uq_automation_execution_event"
        ),
        CheckConstraint("attempt_count >= 0", name="ck_automation_execution_attempts"),
        CheckConstraint(
            "manual_retry_count >= 0", name="ck_automation_execution_manual_retries"
        ),
        Index("ix_automation_executions_claim", "status", "scheduled_for"),
        Index("ix_automation_executions_stale", "status", "started_at"),
        Index(
            "ix_automation_executions_workspace_created", "workspace_id", "created_at"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    automation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(16),
        default=AutomationExecutionStatus.PENDING.value,
        server_default="PENDING",
    )
    scheduled_for: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    manual_retry_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    terminal_failure: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    claimed_by_worker_id: Mapped[str | None] = mapped_column(String(128))
    last_recovered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    failure_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    effect_key: Mapped[str] = mapped_column(String(255), unique=True)


class AutomationWorkerHeartbeat(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "automation_worker_heartbeats"
    __table_args__ = (
        UniqueConstraint("worker_id", name="uq_automation_worker_heartbeat_id"),
        Index("ix_automation_worker_heartbeat_last_seen", "last_heartbeat_at"),
    )

    worker_id: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(
        String(16),
        default=AutomationWorkerState.STARTING.value,
        server_default="STARTING",
    )
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    last_heartbeat_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    last_successful_poll_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    build_identifier: Mapped[str | None] = mapped_column(String(128))
