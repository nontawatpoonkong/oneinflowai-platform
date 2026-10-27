"""Authoritative Hotel vertical catalog and daily inventory models."""

import uuid
from datetime import date, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class Property(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_properties"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_hotel_property_workspace_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    check_in_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    check_out_time: Mapped[time | None] = mapped_column(Time(), nullable=True)


class RoomType(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_room_types"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id"],
            ["hotel_properties.workspace_id", "hotel_properties.id"],
            ondelete="CASCADE",
            name="fk_hotel_room_type_property_workspace",
        ),
        UniqueConstraint("property_id", "code", name="uq_hotel_room_type_code"),
        UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_hotel_room_type_scope"
        ),
        UniqueConstraint(
            "workspace_id", "id", name="uq_hotel_room_type_workspace_id"
        ),
        CheckConstraint("max_adults > 0", name="ck_hotel_room_type_adults"),
        CheckConstraint("max_children >= 0", name="ck_hotel_room_type_children"),
        CheckConstraint("max_occupancy > 0", name="ck_hotel_room_type_occupancy"),
        CheckConstraint("base_capacity > 0", name="ck_hotel_room_type_capacity"),
        CheckConstraint(
            "max_occupancy >= max_adults",
            name="ck_hotel_room_type_occupancy_adults",
        ),
        CheckConstraint(
            "base_capacity <= max_occupancy",
            name="ck_hotel_room_type_base_capacity",
        ),
        CheckConstraint(
            "room_size_sqm IS NULL OR room_size_sqm > 0",
            name="ck_hotel_room_type_size",
        ),
        CheckConstraint(
            "view_type IN ('CITY','GARDEN','POOL','MOUNTAIN','SEA','RIVER',"
            "'COURTYARD','NO_SPECIAL_VIEW','CUSTOM')",
            name="ck_hotel_room_type_view",
        ),
        CheckConstraint(
            "smoking_policy IN ('NON_SMOKING','SMOKING_ALLOWED','DESIGNATED_ONLY')",
            name="ck_hotel_room_type_smoking",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    room_size_sqm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    max_adults: Mapped[int] = mapped_column(Integer)
    max_children: Mapped[int] = mapped_column(Integer, default=0)
    max_occupancy: Mapped[int] = mapped_column(Integer)
    base_capacity: Mapped[int] = mapped_column(Integer)
    smoking_policy: Mapped[str] = mapped_column(
        String(24), default="NON_SMOKING", server_default="NON_SMOKING"
    )
    accessibility_available: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    public_highlights: Mapped[str | None] = mapped_column(Text, nullable=True)
    view_type: Mapped[str] = mapped_column(
        String(24), default="NO_SPECIAL_VIEW", server_default="NO_SPECIAL_VIEW"
    )
    custom_view_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class RatePlan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_rate_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id"],
            [
                "hotel_room_types.workspace_id",
                "hotel_room_types.property_id",
                "hotel_room_types.id",
            ],
            ondelete="CASCADE",
            name="fk_hotel_rate_plan_room_type_scope",
        ),
        UniqueConstraint("room_type_id", "code", name="uq_hotel_rate_plan_code"),
        UniqueConstraint(
            "workspace_id",
            "property_id",
            "room_type_id",
            "id",
            name="uq_hotel_rate_plan_scope",
        ),
        UniqueConstraint(
            "workspace_id", "id", name="uq_hotel_rate_plan_workspace_id"
        ),
        CheckConstraint("base_price >= 0", name="ck_hotel_rate_plan_base_price"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    room_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    refundable: Mapped[bool] = mapped_column(Boolean, default=False)
    cancellation_policy_summary: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class InventoryDate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_inventory_dates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id"],
            [
                "hotel_room_types.workspace_id",
                "hotel_room_types.property_id",
                "hotel_room_types.id",
            ],
            ondelete="CASCADE",
            name="fk_hotel_inventory_room_type_scope",
        ),
        UniqueConstraint(
            "room_type_id", "inventory_date", name="uq_hotel_inventory_room_date"
        ),
        CheckConstraint("total_units >= 0", name="ck_hotel_inventory_total"),
        CheckConstraint("reserved_units >= 0", name="ck_hotel_inventory_reserved"),
        CheckConstraint("blocked_units >= 0", name="ck_hotel_inventory_blocked"),
        CheckConstraint(
            "reserved_units + blocked_units <= total_units",
            name="ck_hotel_inventory_capacity",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    room_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    inventory_date: Mapped[date] = mapped_column(Date, index=True)
    total_units: Mapped[int] = mapped_column(Integer)
    reserved_units: Mapped[int] = mapped_column(Integer, default=0)
    blocked_units: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def available_units(self) -> int:
        return self.total_units - self.reserved_units - self.blocked_units
