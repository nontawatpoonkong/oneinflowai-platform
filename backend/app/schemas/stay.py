"""Typed Hotel room and Stay operations contracts."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.stay import (
    RoomOperationalStatus,
    RoomReadinessStatus,
    StayEventType,
    StayStatus,
)


class RoomCreate(BaseModel):
    property_id: uuid.UUID
    room_type_id: uuid.UUID
    code: str = Field(min_length=1, max_length=64)
    floor: str | None = Field(default=None, max_length=32)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("room code cannot be blank")
        return value


class RoomUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    floor: str | None = Field(default=None, max_length=32)
    active: bool | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    property_id: uuid.UUID
    property_name: str
    room_type_id: uuid.UUID
    room_type_name: str
    code: str
    floor: str | None
    active: bool
    operational_status: RoomOperationalStatus
    readiness_status: RoomReadinessStatus
    current_stay_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class RoomAssignmentRequest(BaseModel):
    room_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)

    @field_validator("room_ids")
    @classmethod
    def unique_rooms(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("room_ids must be unique")
        return value


class CheckInRequest(BaseModel):
    room_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("room_ids")
    @classmethod
    def unique_rooms(cls, value: list[uuid.UUID] | None):
        if value is not None and len(set(value)) != len(value):
            raise ValueError("room_ids must be unique")
        return value


class StayRoomSummary(BaseModel):
    assignment_id: uuid.UUID
    room_id: uuid.UUID
    code: str
    room_type_id: uuid.UUID
    operational_status: RoomOperationalStatus
    readiness_status: RoomReadinessStatus
    assigned_at: datetime
    released_at: datetime | None


class StayEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: StayEventType
    room_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    event_metadata: dict
    sequence: int
    created_at: datetime


class StayResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    booking_id: uuid.UUID
    property_id: uuid.UUID
    property_name: str
    room_type_id: uuid.UUID
    customer_id: uuid.UUID | None
    guest_name: str | None
    status: StayStatus
    planned_check_in_date: date
    planned_check_out_date: date
    required_room_count: int
    actual_check_in_at: datetime | None
    actual_check_out_at: datetime | None
    rooms: list[StayRoomSummary]
    events: list[StayEventResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class StayListResponse(BaseModel):
    items: list[StayResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RoomListResponse(BaseModel):
    items: list[RoomResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
