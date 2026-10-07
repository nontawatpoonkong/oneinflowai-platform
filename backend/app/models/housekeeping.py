"""Workspace-scoped housekeeping tasks and immutable audit events."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
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


class HousekeepingTaskStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class HousekeepingPriority(enum.StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class HousekeepingEventType(enum.StrEnum):
    ROOM_DIRTY = "ROOM_DIRTY"
    HOUSEKEEPING_TASK_CREATED = "HOUSEKEEPING_TASK_CREATED"
    HOUSEKEEPING_ASSIGNED = "HOUSEKEEPING_ASSIGNED"
    HOUSEKEEPING_STARTED = "HOUSEKEEPING_STARTED"
    HOUSEKEEPING_COMPLETED = "HOUSEKEEPING_COMPLETED"
    ROOM_READY = "ROOM_READY"
    HOUSEKEEPING_CANCELLED = "HOUSEKEEPING_CANCELLED"


def _enum(cls, name):
    return SAEnum(
        cls, name=name, values_callable=lambda values: [item.value for item in values]
    )


class HousekeepingTask(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_housekeeping_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_id"],
            ["hotel_rooms.workspace_id", "hotel_rooms.property_id", "hotel_rooms.id"],
            name="fk_housekeeping_task_room_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "stay_id"],
            ["hotel_stays.workspace_id", "hotel_stays.property_id", "hotel_stays.id"],
            name="fk_housekeeping_task_stay_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "workspace_id",
            "stay_id",
            "room_id",
            "source",
            name="uq_housekeeping_checkout_task",
        ),
        UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_housekeeping_task_scope"
        ),
        Index(
            "uq_housekeeping_active_room",
            "room_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'IN_PROGRESS')"),
        ),
        Index("ix_housekeeping_workspace_status", "workspace_id", "status"),
        Index("ix_housekeeping_property_status", "property_id", "status"),
        Index("ix_housekeeping_assignee_status", "assigned_to_user_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stay_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[HousekeepingTaskStatus] = mapped_column(
        _enum(HousekeepingTaskStatus, "hotel_housekeeping_task_status"),
        default=HousekeepingTaskStatus.PENDING,
    )
    priority: Mapped[HousekeepingPriority] = mapped_column(
        _enum(HousekeepingPriority, "hotel_housekeeping_priority"),
        default=HousekeepingPriority.NORMAL,
    )
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(32), default="CHECKOUT")
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class HousekeepingEvent(UUIDMixin, Base):
    __tablename__ = "hotel_housekeeping_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "task_id"],
            [
                "hotel_housekeeping_tasks.workspace_id",
                "hotel_housekeeping_tasks.property_id",
                "hotel_housekeeping_tasks.id",
            ],
            name="fk_housekeeping_event_task_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_housekeeping_events_task_sequence", "task_id", "sequence"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[HousekeepingEventType] = mapped_column(
        _enum(HousekeepingEventType, "hotel_housekeeping_event_type")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class RoomReadinessOverrideEvent(UUIDMixin, Base):
    __tablename__ = "hotel_room_readiness_override_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_id"],
            ["hotel_rooms.workspace_id", "hotel_rooms.property_id", "hotel_rooms.id"],
            name="fk_readiness_override_room_scope",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_readiness_override_workspace_room_sequence",
            "workspace_id",
            "room_id",
            "sequence",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    previous_readiness: Mapped[str] = mapped_column(String(16))
    new_readiness: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
