"""Action collection API schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.action_collection import ActionCollectionStatus


class ActionCollectionCreate(BaseModel):
    action_definition_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    initial_input: str | None = Field(default=None, min_length=1, max_length=10_000)
    fields: dict[str, Any] = Field(default_factory=dict)


class ActionCollectionInput(BaseModel):
    input: str | None = Field(default=None, min_length=1, max_length=10_000)
    fields: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_input(self):
        if self.input is None and not self.fields:
            raise ValueError("input or fields is required")
        return self


class ActionCollectionConfirm(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=512)


class ActionCollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_definition_id: uuid.UUID
    conversation_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    action_request_id: uuid.UUID | None
    status: ActionCollectionStatus
    collected_payload: dict[str, Any]
    missing_fields: list[str]
    invalid_fields: dict[str, str]
    expires_at: datetime
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionCollectionResult(BaseModel):
    session: ActionCollectionResponse
    missing_field_metadata: list[dict[str, Any]] = Field(default_factory=list)
    confirmation_summary: dict[str, Any] | None = None
    confirmation_token: str | None = None
    next_step: str
    action: dict[str, Any] | None = None
