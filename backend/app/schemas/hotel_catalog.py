"""Rich Hotel room catalog and bounded availability calendar contracts."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.hotel_catalog import AmenityValueType, BedType, RoomImageCategory
from app.schemas.hotel import RoomTypeCreate


def _plain_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if "<" in normalized or ">" in normalized:
        raise ValueError("HTML is not allowed")
    return normalized


class RoomTypeBedInput(BaseModel):
    bed_type: BedType
    quantity: int = Field(gt=0, le=20)
    custom_label: str | None = Field(default=None, max_length=120)
    width_cm: int | None = Field(default=None, gt=0, le=500)
    length_cm: int | None = Field(default=None, gt=0, le=500)
    sort_order: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def custom_label_matches_type(self):
        if self.bed_type is BedType.OTHER and not self.custom_label:
            raise ValueError("custom_label is required for OTHER bed type")
        if self.bed_type is not BedType.OTHER and self.custom_label is not None:
            raise ValueError("custom_label is only valid for OTHER bed type")
        self.custom_label = _plain_text(self.custom_label)
        return self


class RoomTypeBedResponse(RoomTypeBedInput):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class AmenityDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    category: str
    default_name_en: str
    default_name_th: str
    value_type: AmenityValueType
    active: bool
    sort_order: int


class RoomTypeAmenityInput(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    boolean_value: bool | None = None
    number_value: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
    text_value: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def exactly_one_value(self):
        if (
            sum(
                item is not None
                for item in (self.boolean_value, self.number_value, self.text_value)
            )
            != 1
        ):
            raise ValueError("exactly one amenity value is required")
        self.text_value = _plain_text(self.text_value)
        return self


class RoomTypeAmenityResponse(RoomTypeAmenityInput):
    id: uuid.UUID
    amenity_definition_id: uuid.UUID
    category: str
    name_en: str
    name_th: str
    value_type: AmenityValueType


class RoomTypeImageCreate(BaseModel):
    caption: str | None = Field(default=None, max_length=300)
    alt_text: str = Field(min_length=1, max_length=300)
    image_category: RoomImageCategory = RoomImageCategory.ROOM
    sort_order: int = Field(default=0, ge=0, le=1000)
    is_cover: bool = False

    @field_validator("caption", "alt_text")
    @classmethod
    def safe_text(cls, value):
        return _plain_text(value)


class RoomTypeImageResponse(RoomTypeImageCreate):
    id: uuid.UUID
    room_type_id: uuid.UUID
    public_url: str | None
    content_url: str
    mime_type: str


class RoomTypeImageOrderItem(BaseModel):
    image_id: uuid.UUID
    sort_order: int = Field(ge=0, le=1000)
    is_cover: bool = False


class PhysicalRoomInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    floor: str | None = Field(default=None, max_length=32)
    building: str | None = Field(default=None, max_length=80)
    wing: str | None = Field(default=None, max_length=80)
    internal_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("room code cannot be blank")
        return value


class RichRoomTypeCreate(RoomTypeCreate):
    beds: list[RoomTypeBedInput] = Field(default_factory=list, max_length=12)
    amenities: list[RoomTypeAmenityInput] = Field(default_factory=list, max_length=100)
    physical_rooms: list[PhysicalRoomInput] = Field(
        default_factory=list, max_length=500
    )

    @model_validator(mode="after")
    def room_scope_matches(self):
        codes = [room.code.casefold() for room in self.physical_rooms]
        if len(codes) != len(set(codes)):
            raise ValueError("physical room codes must be unique")
        return self


class RoomCatalogDetail(BaseModel):
    room_type: dict
    beds: list[RoomTypeBedResponse]
    amenities: list[RoomTypeAmenityResponse]
    images: list[RoomTypeImageResponse]
    physical_room_count: int


class AvailabilityCalendarCell(BaseModel):
    date: date
    total_units: int
    reserved_units: int
    blocked_units: int
    available_units: int
    used_units: int
    occupancy_ratio: Decimal
    color_bucket: str
    authority: str
    has_inventory: bool


class AvailabilityCalendarRow(BaseModel):
    room_type_id: uuid.UUID
    room_type_name: str
    cells: list[AvailabilityCalendarCell]


class AvailabilityCalendarResponse(BaseModel):
    property_id: uuid.UUID
    start_date: date
    days: int
    rows: list[AvailabilityCalendarRow]


class CustomerRoomFacts(BaseModel):
    room_type_id: uuid.UUID
    name: str
    short_description: str | None
    description: str | None
    room_size_sqm: Decimal | None
    max_adults: int
    max_children: int
    max_occupancy: int
    smoking_policy: str
    accessibility_available: bool
    public_highlights: str | None
    view_type: str
    custom_view_label: str | None
    beds: list[RoomTypeBedResponse]
    amenities: list[RoomTypeAmenityResponse]
    images: list[RoomTypeImageResponse]
    physical_room_count: int
