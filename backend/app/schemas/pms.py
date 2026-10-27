"""PMS operational API schemas; credentials never appear in responses."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.pms import (
    PMSConnectionStatus,
    PMSEntityType,
    PMSInventoryAuthority,
    PMSIssueStatus,
    PMSSyncMode,
    PMSSyncRunStatus,
)


class PMSConnectionCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    credentials: dict[str, str] = Field(default_factory=dict)
    external_account_id: str | None = Field(default=None, max_length=255)
    sync_mode: PMSSyncMode = PMSSyncMode.READ_ONLY_IMPORT
    inventory_authority: PMSInventoryAuthority = PMSInventoryAuthority.LOCAL

    @field_validator("credentials")
    @classmethod
    def bounded_credentials(cls, value: dict[str, str]):
        if len(value) > 20 or any(
            not key or len(key) > 128 or not isinstance(item, str) or len(item) > 4096
            for key, item in value.items()
        ):
            raise ValueError("PMS credentials are invalid")
        return value


class PMSConnectionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    active: bool | None = None
    inventory_authority: PMSInventoryAuthority | None = None
    credentials: dict[str, str] | None = None

    @field_validator("credentials")
    @classmethod
    def bounded_credentials(cls, value: dict[str, str] | None):
        if value is not None and (
            len(value) > 20
            or any(
                not key
                or len(key) > 128
                or not isinstance(item, str)
                or len(item) > 4096
                for key, item in value.items()
            )
        ):
            raise ValueError("PMS credentials are invalid")
        return value


class PMSProviderCapabilitiesResponse(BaseModel):
    properties: bool
    room_types: bool
    physical_rooms: bool
    rate_plans: bool
    inventory: bool
    reservations: bool
    incremental_sync: bool
    pagination: bool


class PMSConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    provider: str
    name: str
    active: bool
    status: PMSConnectionStatus
    external_account_id: str | None
    sync_mode: PMSSyncMode
    inventory_authority: PMSInventoryAuthority
    last_successful_sync_at: datetime | None
    last_failed_sync_at: datetime | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime


class PMSMappingCreate(BaseModel):
    connection_id: uuid.UUID
    entity_type: PMSEntityType
    external_id: str = Field(min_length=1, max_length=255)
    local_entity_id: uuid.UUID
    external_version: str | None = Field(default=None, max_length=255)
    external_updated_at: datetime | None = None


class PMSMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    connection_id: uuid.UUID
    entity_type: PMSEntityType
    external_id: str
    local_entity_id: uuid.UUID
    external_version: str | None
    external_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PMSSyncRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    connection_id: uuid.UUID
    status: PMSSyncRunStatus
    started_at: datetime | None
    completed_at: datetime | None
    cursor_before: dict[str, Any]
    cursor_after: dict[str, Any] | None
    entities_fetched: int
    entities_applied: int
    conflict_count: int
    warning_count: int
    error_code: str | None
    initiated_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PMSReconciliationIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    connection_id: uuid.UUID
    sync_run_id: uuid.UUID
    entity_type: PMSEntityType
    external_id: str
    local_entity_id: uuid.UUID | None
    issue_type: str
    severity: str
    status: PMSIssueStatus
    details: dict[str, Any]
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
