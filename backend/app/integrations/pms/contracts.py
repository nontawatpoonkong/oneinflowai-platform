"""Strict provider-neutral contracts for read-only PMS imports."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StrictImport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PMSProviderCapabilities(StrictImport):
    properties: bool = False
    room_types: bool = False
    physical_rooms: bool = False
    rate_plans: bool = False
    inventory: bool = False
    reservations: bool = False
    incremental_sync: bool = False
    pagination: bool = False


class ImportedProperty(StrictImport):
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    external_version: str | None = Field(default=None, max_length=255)
    external_updated_at: datetime | None = None


class ImportedRoomType(StrictImport):
    external_id: str = Field(min_length=1, max_length=255)
    property_external_id: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    external_version: str | None = Field(default=None, max_length=255)
    external_updated_at: datetime | None = None


class ImportedRoom(StrictImport):
    external_id: str = Field(min_length=1, max_length=255)
    property_external_id: str = Field(min_length=1, max_length=255)
    room_type_external_id: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    floor: str | None = Field(default=None, max_length=32)
    external_version: str | None = Field(default=None, max_length=255)
    external_updated_at: datetime | None = None


class ImportedRatePlan(StrictImport):
    external_id: str = Field(min_length=1, max_length=255)
    property_external_id: str = Field(min_length=1, max_length=255)
    room_type_external_id: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    base_price: Decimal | None = Field(default=None, ge=0)
    external_version: str | None = Field(default=None, max_length=255)
    external_updated_at: datetime | None = None


class ImportedInventoryDay(StrictImport):
    property_external_id: str = Field(min_length=1, max_length=255)
    room_type_external_id: str = Field(min_length=1, max_length=255)
    inventory_date: date
    total_units: int = Field(ge=0)
    sellable_units: int | None = Field(default=None, ge=0)
    external_version: str | None = Field(default=None, max_length=255)
    external_updated_at: datetime | None = None


class ImportedReservation(StrictImport):
    """Normalized seam only; Sprint 10.8 deliberately does not apply these."""

    external_id: str = Field(min_length=1, max_length=255)
    property_external_id: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=64)
    arrival_date: date
    departure_date: date
    external_version: str | None = Field(default=None, max_length=255)
    external_updated_at: datetime | None = None


class PMSImportPage[T: StrictImport](StrictImport):
    items: tuple[T, ...] = ()
    next_cursor: str | None = Field(default=None, max_length=2048)


class PMSConnectionTestResult(StrictImport):
    account_id: str | None = Field(default=None, max_length=255)
    account_name: str | None = Field(default=None, max_length=255)
