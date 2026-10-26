"""Typed Hotel vertical management and availability contracts."""

import re
import uuid
from contextlib import suppress
from datetime import date, time
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,63}$")
_IANA_TIMEZONE = re.compile(
    r"^(?:UTC|[A-Za-z][A-Za-z0-9._+-]*/[A-Za-z][A-Za-z0-9._+-]*)$"
)


def _validate_timezone(value: str) -> str:
    if not _IANA_TIMEZONE.fullmatch(value):
        raise ValueError("timezone must be an IANA timezone name")
    with suppress(ZoneInfoNotFoundError):
        ZoneInfo(value)
        # Windows Python installations do not always ship the optional IANA
        # database. Preserve strict name syntax here; deployments with tzdata
        # installed additionally verify that the zone exists.
    return value


class PropertyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=_CURRENCY.pattern)
    active: bool = True
    check_in_time: time | None = None
    check_out_time: time | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        return _validate_timezone(value)


class PropertyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, pattern=_CURRENCY.pattern)
    active: bool | None = None
    check_in_time: time | None = None
    check_out_time: time | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            return _validate_timezone(value)
        return value


class PropertyResponse(PropertyCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID


class RoomTypeCreate(BaseModel):
    property_id: uuid.UUID
    code: str = Field(pattern=_CODE.pattern)
    name: str = Field(min_length=1, max_length=255)
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    room_size_sqm: Decimal | None = Field(
        default=None, gt=0, max_digits=7, decimal_places=2
    )
    max_adults: int = Field(gt=0)
    max_children: int = Field(default=0, ge=0)
    max_occupancy: int = Field(gt=0)
    base_capacity: int = Field(gt=0)
    smoking_policy: str = Field(
        default="NON_SMOKING",
        pattern=r"^(NON_SMOKING|SMOKING_ALLOWED|DESIGNATED_ONLY)$",
    )
    accessibility_available: bool = False
    public_highlights: str | None = Field(default=None, max_length=2000)
    view_type: str = Field(
        default="NO_SPECIAL_VIEW",
        pattern=(
            r"^(CITY|GARDEN|POOL|MOUNTAIN|SEA|RIVER|COURTYARD|"
            r"NO_SPECIAL_VIEW|CUSTOM)$"
        ),
    )
    custom_view_label: str | None = Field(default=None, max_length=120)
    active: bool = True

    @model_validator(mode="after")
    def occupancy_consistent(self):
        if self.max_occupancy < self.max_adults:
            raise ValueError("max_occupancy must be at least max_adults")
        if self.base_capacity > self.max_occupancy:
            raise ValueError("base_capacity cannot exceed max_occupancy")
        if self.view_type == "CUSTOM" and not self.custom_view_label:
            raise ValueError("custom_view_label is required for CUSTOM view")
        if self.view_type != "CUSTOM" and self.custom_view_label is not None:
            raise ValueError("custom_view_label is only valid for CUSTOM view")
        return self


class RoomTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    room_size_sqm: Decimal | None = Field(
        default=None, gt=0, max_digits=7, decimal_places=2
    )
    max_adults: int | None = Field(default=None, gt=0)
    max_children: int | None = Field(default=None, ge=0)
    max_occupancy: int | None = Field(default=None, gt=0)
    base_capacity: int | None = Field(default=None, gt=0)
    smoking_policy: str | None = Field(
        default=None,
        pattern=r"^(NON_SMOKING|SMOKING_ALLOWED|DESIGNATED_ONLY)$",
    )
    accessibility_available: bool | None = None
    public_highlights: str | None = Field(default=None, max_length=2000)
    view_type: str | None = Field(
        default=None,
        pattern=(
            r"^(CITY|GARDEN|POOL|MOUNTAIN|SEA|RIVER|COURTYARD|"
            r"NO_SPECIAL_VIEW|CUSTOM)$"
        ),
    )
    custom_view_label: str | None = Field(default=None, max_length=120)
    active: bool | None = None


class RoomTypeResponse(RoomTypeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID


class RatePlanCreate(BaseModel):
    property_id: uuid.UUID
    room_type_id: uuid.UUID
    code: str = Field(pattern=_CODE.pattern)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    currency: str = Field(pattern=_CURRENCY.pattern)
    base_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    refundable: bool = False
    cancellation_policy_summary: str | None = Field(default=None, max_length=500)
    active: bool = True


class RatePlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    currency: str | None = Field(default=None, pattern=_CURRENCY.pattern)
    base_price: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    refundable: bool | None = None
    cancellation_policy_summary: str | None = Field(default=None, max_length=500)
    active: bool | None = None


class RatePlanResponse(RatePlanCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID


class InventoryUpsert(BaseModel):
    property_id: uuid.UUID
    room_type_id: uuid.UUID
    start_date: date
    end_date: date
    total_units: int = Field(ge=0)
    reserved_units: int = Field(default=0, ge=0)
    blocked_units: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_range_and_capacity(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.reserved_units + self.blocked_units > self.total_units:
            raise ValueError("reserved_units + blocked_units cannot exceed total_units")
        return self


class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    property_id: uuid.UUID
    room_type_id: uuid.UUID
    inventory_date: date
    total_units: int
    reserved_units: int
    blocked_units: int
    available_units: int


class AvailabilitySearchRequest(BaseModel):
    property_id: uuid.UUID
    check_in: date
    check_out: date
    adults: int = Field(gt=0)
    children: int = Field(default=0, ge=0)
    room_type_id: uuid.UUID | None = None
    rate_plan_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def valid_stay(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class NightlyRate(BaseModel):
    date: date
    amount: Decimal


class RoomAvailabilityResult(BaseModel):
    property_id: uuid.UUID
    room_type_id: uuid.UUID
    room_type_name: str
    rate_plan_id: uuid.UUID
    rate_plan_name: str
    currency: str
    nightly_rates: list[NightlyRate]
    subtotal: Decimal
    available_units: int
    max_adults: int
    max_children: int
    max_occupancy: int
    refundable: bool
    cancellation_policy_summary: str | None


class AvailabilitySearchResponse(BaseModel):
    check_in: date
    check_out: date
    nights: int
    results: list[RoomAvailabilityResult]
