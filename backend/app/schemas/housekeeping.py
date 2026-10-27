"""Housekeeping API contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.housekeeping import (
    HousekeepingEventType,
    HousekeepingPriority,
    HousekeepingTaskStatus,
)
from app.models.stay import RoomOperationalStatus, RoomReadinessStatus


class HousekeepingAssignRequest(BaseModel):
    assigned_to_user_id: uuid.UUID


class RoomReadinessOverrideRequest(BaseModel):
    readiness_status: RoomReadinessStatus
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("reason must contain at least 10 characters")
        return value


class HousekeepingEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: HousekeepingEventType
    actor_user_id: uuid.UUID | None
    event_metadata: dict
    sequence: int
    created_at: datetime


class HousekeepingTaskResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    property_id: uuid.UUID
    property_name: str
    room_id: uuid.UUID
    room_code: str
    room_type_name: str
    stay_id: uuid.UUID | None
    status: HousekeepingTaskStatus
    priority: HousekeepingPriority
    assigned_to_user_id: uuid.UUID | None
    source: str
    operational_status: RoomOperationalStatus
    readiness_status: RoomReadinessStatus
    checkout_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    events: list[HousekeepingEventResponse] = Field(default_factory=list)


class HousekeepingTaskListResponse(BaseModel):
    items: list[HousekeepingTaskResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RoomReadinessOverrideEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    property_id: uuid.UUID
    room_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    previous_readiness: str
    new_readiness: str
    reason: str
    sequence: int
    created_at: datetime


class RoomReadinessOverrideResponse(BaseModel):
    room_id: uuid.UUID
    operational_status: RoomOperationalStatus
    readiness_status: RoomReadinessStatus
    event: RoomReadinessOverrideEventResponse
