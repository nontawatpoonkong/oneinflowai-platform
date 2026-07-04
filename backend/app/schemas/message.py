"""Message schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.message import MessageType, SenderType


class MessageCreate(BaseModel):
    sender_type: SenderType
    sender_id: uuid.UUID | None = None
    content: str
    message_type: MessageType = MessageType.TEXT
    metadata: dict[str, Any] = Field(default_factory=dict)
    external_message_id: str | None = Field(default=None, max_length=255)

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("content cannot be empty")
            return stripped
        return value

    @field_validator("external_message_id", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: SenderType
    sender_id: uuid.UUID | None
    content: str
    message_type: MessageType
    metadata: dict[str, Any]
    external_message_id: str | None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
