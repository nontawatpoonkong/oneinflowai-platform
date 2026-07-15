"""Conversation schemas."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.channels import ChannelType
from app.models.conversation import ConversationMode, ConversationStatus


def _trim_optional(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class ConversationSortField(enum.StrEnum):
    LAST_MESSAGE_AT = "last_message_at"
    CREATED_AT = "created_at"


class ConversationCreate(BaseModel):
    customer_id: uuid.UUID
    channel: ChannelType
    subject: str | None = Field(default=None, max_length=255)
    assigned_user_id: uuid.UUID | None = None
    external_conversation_id: str | None = Field(default=None, max_length=255)
    status: ConversationStatus = ConversationStatus.OPEN

    @field_validator("subject", "external_conversation_id", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        return _trim_optional(value)


class ConversationUpdate(BaseModel):
    status: ConversationStatus | None = None
    subject: str | None = Field(default=None, max_length=255)
    assigned_user_id: uuid.UUID | None = None
    ai_mode: ConversationMode | None = None

    @field_validator("subject", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        return _trim_optional(value)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    status: ConversationStatus
    channel: ChannelType
    subject: str | None
    assigned_user_id: uuid.UUID | None
    external_conversation_id: str | None
    last_message_at: datetime | None
    ai_mode: ConversationMode
    taken_over_by: uuid.UUID | None
    taken_over_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
