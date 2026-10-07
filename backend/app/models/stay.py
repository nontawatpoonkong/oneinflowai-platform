"""Physical Hotel rooms, operational stays, assignments, and immutable events."""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
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


class RoomOperationalStatus(enum.StrEnum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class RoomReadinessStatus(enum.StrEnum):
    READY = "READY"
    DIRTY = "DIRTY"
    CLEANING = "CLEANING"


class StayStatus(enum.StrEnum):
    EXPECTED = "EXPECTED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    NO_SHOW = "NO_SHOW"


class StayEventType(enum.StrEnum):
    STAY_CREATED = "STAY_CREATED"
    ROOM_ASSIGNED = "ROOM_ASSIGNED"
    ROOM_UNASSIGNED = "ROOM_UNASSIGNED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    NO_SHOW = "NO_SHOW"


def _enum(cls, name):
    return SAEnum(
        cls, name=name, values_callable=lambda values: [item.value for item in values]
    )


class HotelRoom(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_rooms"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id"],
            ["hotel_properties.workspace_id", "hotel_properties.id"],
            ondelete="RESTRICT",
            name="fk_hotel_room_property_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id"],
            [
                "hotel_room_types.workspace_id",
                "hotel_room_types.property_id",
                "hotel_room_types.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_room_type_scope",
        ),
        UniqueConstraint(
            "workspace_id", "property_id", "code", name="uq_hotel_room_code"
        ),
        UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_hotel_room_scope"
        ),
        Index("ix_hotel_rooms_workspace_status", "workspace_id", "operational_status"),
        Index("ix_hotel_rooms_property_status", "property_id", "operational_status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    room_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String(64))
    floor: Mapped[str | None] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    operational_status: Mapped[RoomOperationalStatus] = mapped_column(
        _enum(RoomOperationalStatus, "hotel_room_operational_status"),
        default=RoomOperationalStatus.AVAILABLE,
        server_default=RoomOperationalStatus.AVAILABLE.value,
    )
    readiness_status: Mapped[RoomReadinessStatus] = mapped_column(
        _enum(RoomReadinessStatus, "hotel_room_readiness_status"),
        default=RoomReadinessStatus.READY,
        server_default=RoomReadinessStatus.READY.value,
    )


class Stay(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_stays"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "booking_id"],
            [
                "hotel_bookings.workspace_id",
                "hotel_bookings.property_id",
                "hotel_bookings.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_stay_booking_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="RESTRICT",
            name="fk_hotel_stay_customer_scope",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_hotel_stay_scope"),
        UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_hotel_stay_property_scope"
        ),
        UniqueConstraint("workspace_id", "booking_id", name="uq_hotel_stay_booking"),
        CheckConstraint(
            "planned_check_out_date > planned_check_in_date",
            name="ck_hotel_stay_dates",
        ),
        CheckConstraint("required_room_count > 0", name="ck_hotel_stay_room_count"),
        Index("ix_hotel_stays_workspace_status", "workspace_id", "status"),
        Index("ix_hotel_stays_property_status", "property_id", "status"),
        Index("ix_hotel_stays_customer", "workspace_id", "customer_id"),
        Index("ix_hotel_stays_arrival", "workspace_id", "planned_check_in_date"),
        Index("ix_hotel_stays_departure", "workspace_id", "planned_check_out_date"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[StayStatus] = mapped_column(
        _enum(StayStatus, "hotel_stay_status"), default=StayStatus.EXPECTED
    )
    planned_check_in_date: Mapped[date] = mapped_column(Date)
    planned_check_out_date: Mapped[date] = mapped_column(Date)
    required_room_count: Mapped[int] = mapped_column(Integer)
    actual_check_in_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    actual_check_out_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )


class StayRoomAssignment(UUIDMixin, Base):
    __tablename__ = "hotel_stay_room_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "stay_id"],
            [
                "hotel_stays.workspace_id",
                "hotel_stays.property_id",
                "hotel_stays.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_stay_assignment_stay_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_id"],
            ["hotel_rooms.workspace_id", "hotel_rooms.property_id", "hotel_rooms.id"],
            ondelete="RESTRICT",
            name="fk_hotel_stay_assignment_room_scope",
        ),
        Index(
            "uq_hotel_room_active_assignment",
            "room_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
        Index(
            "ix_hotel_stay_assignments_active",
            "workspace_id",
            "stay_id",
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stay_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class StayEvent(UUIDMixin, Base):
    __tablename__ = "hotel_stay_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "stay_id"],
            [
                "hotel_stays.workspace_id",
                "hotel_stays.property_id",
                "hotel_stays.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_stay_event_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_id"],
            ["hotel_rooms.workspace_id", "hotel_rooms.property_id", "hotel_rooms.id"],
            ondelete="RESTRICT",
            name="fk_hotel_stay_event_room_scope",
        ),
        Index("ix_hotel_stay_events_stay_sequence", "stay_id", "sequence"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stay_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[StayEventType] = mapped_column(
        _enum(StayEventType, "hotel_stay_event_type")
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
