"""Public-safe AI tool action contracts."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.ai_tool import (
    AIToolActionStatus,
    AIToolClassification,
)


class AIToolActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    customer_id: uuid.UUID
    tool_name: str
    tool_version: str
    classification: AIToolClassification
    status: AIToolActionStatus
    confirmation_required: bool
    confirmation_expires_at: datetime | None
    confirmed_at: datetime | None
    executed_at: datetime | None
    cancelled_at: datetime | None
    result: dict[str, Any] | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class AIToolConfirmationRequest(BaseModel):
    client_message_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )
    confirmation_token: str = Field(min_length=32, max_length=512)


class AIToolCancellationRequest(BaseModel):
    client_message_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )
