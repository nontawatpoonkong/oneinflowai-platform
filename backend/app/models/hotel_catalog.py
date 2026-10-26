"""Structured customer-facing room catalog metadata."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class BedType(enum.StrEnum):
    KING = "KING"
    QUEEN = "QUEEN"
    DOUBLE = "DOUBLE"
    TWIN = "TWIN"
    SINGLE = "SINGLE"
    BUNK = "BUNK"
    SOFA_BED = "SOFA_BED"
    FUTON = "FUTON"
    OTHER = "OTHER"


class AmenityValueType(enum.StrEnum):
    BOOLEAN = "BOOLEAN"
    NUMBER = "NUMBER"
    TEXT = "TEXT"


class RoomImageCategory(enum.StrEnum):
    ROOM = "ROOM"
    BED = "BED"
    BATHROOM = "BATHROOM"
    VIEW = "VIEW"
    BALCONY = "BALCONY"
    AMENITY = "AMENITY"
    OTHER = "OTHER"


class RoomTypeBed(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_room_type_beds"
    __table_args__ = (
        UniqueConstraint("room_type_id", "sort_order", name="uq_room_type_bed_order"),
        CheckConstraint("quantity > 0", name="ck_room_type_bed_quantity"),
        CheckConstraint(
            "width_cm IS NULL OR width_cm > 0", name="ck_room_type_bed_width"
        ),
        CheckConstraint(
            "length_cm IS NULL OR length_cm > 0", name="ck_room_type_bed_length"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hotel_room_types.id", ondelete="CASCADE"),
        index=True,
    )
    bed_type: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[int] = mapped_column(Integer)
    custom_label: Mapped[str | None] = mapped_column(String(120))
    width_cm: Mapped[int | None] = mapped_column(Integer)
    length_cm: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class AmenityDefinition(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_amenity_definitions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_hotel_amenity_code"),
        CheckConstraint(
            "value_type IN ('BOOLEAN','NUMBER','TEXT')",
            name="ck_hotel_amenity_value_type",
        ),
    )

    code: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40), index=True)
    default_name_en: Mapped[str] = mapped_column(String(160))
    default_name_th: Mapped[str] = mapped_column(String(160))
    value_type: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class RoomTypeAmenity(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_room_type_amenities"
    __table_args__ = (
        UniqueConstraint(
            "room_type_id", "amenity_definition_id", name="uq_room_type_amenity"
        ),
        CheckConstraint(
            "num_nonnulls(boolean_value, number_value, text_value) = 1",
            name="ck_room_type_amenity_one_value",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hotel_room_types.id", ondelete="CASCADE"),
        index=True,
    )
    amenity_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hotel_amenity_definitions.id", ondelete="RESTRICT"),
    )
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    number_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    text_value: Mapped[str | None] = mapped_column(Text)


class RoomTypeImage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "hotel_room_type_images"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_room_type_image_storage_key"),
        UniqueConstraint("room_type_id", "sort_order", name="uq_room_type_image_order"),
        Index(
            "uq_room_type_image_cover",
            "room_type_id",
            unique=True,
            postgresql_where=text("is_cover"),
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hotel_room_types.id", ondelete="CASCADE"),
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(512))
    public_url: Mapped[str | None] = mapped_column(String(1000))
    mime_type: Mapped[str] = mapped_column(String(80))
    caption: Mapped[str | None] = mapped_column(String(300))
    alt_text: Mapped[str] = mapped_column(String(300))
    image_category: Mapped[str] = mapped_column(String(24))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_cover: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
