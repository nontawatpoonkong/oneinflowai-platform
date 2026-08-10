"""Fulfillment queue request and response schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.action import ActionExecutionMode, ActionPriority, ActionRequestStatus


class ActionFieldDefinition(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=255)
    type: Literal["string", "integer", "number", "boolean", "enum"]
    required: bool
    values: list[str | int | float] | None = None

    @field_validator("values")
    @classmethod
    def enum_requires_values(cls, value, info):
        if info.data.get("type") == "enum" and not value:
            raise ValueError("enum fields require values")
        return value


class ActionDefinitionCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    execution_mode: ActionExecutionMode = ActionExecutionMode.MANUAL
    required_fields: list[ActionFieldDefinition] = Field(default_factory=list)
    optional_fields: list[ActionFieldDefinition] = Field(default_factory=list)
    is_active: bool = True


class ActionDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    execution_mode: ActionExecutionMode | None = None
    required_fields: list[ActionFieldDefinition] | None = None
    optional_fields: list[ActionFieldDefinition] | None = None
    is_active: bool | None = None


class ActionDefinitionResponse(ActionDefinitionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ActionCreate(BaseModel):
    action_definition_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    priority: ActionPriority = ActionPriority.NORMAL
    payload: dict[str, Any]
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class ActionAssign(BaseModel):
    user_id: uuid.UUID


class ActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    action_definition_id: uuid.UUID
    conversation_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    status: ActionRequestStatus
    priority: ActionPriority
    payload: dict[str, Any]
    created_by_type: str
    created_by_user_id: uuid.UUID | None
    assigned_to_user_id: uuid.UUID | None
    idempotency_key: str | None
    assigned_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionListResponse(BaseModel):
    items: list[ActionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
