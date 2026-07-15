"""Public WebChat request/response schemas."""

import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.message import MessageListResponse, MessageResponse


def _trim(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class WebChatSessionCreate(BaseModel):
    workspace_key: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    language: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    landing_url: str | None = Field(default=None, max_length=2048)
    referrer: str | None = Field(default=None, max_length=2048)

    @field_validator("workspace_key", "name", mode="before")
    @classmethod
    def trim_required(cls, value: object) -> object:
        return _trim(value)

    @field_validator(
        "phone", "language", "timezone", "landing_url", "referrer", mode="before"
    )
    @classmethod
    def trim_optional(cls, value: object) -> object:
        trimmed = _trim(value)
        return trimmed or None


class WebChatSessionResponse(BaseModel):
    conversation_id: uuid.UUID
    session_token: str


class WebChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value: object) -> object:
        return _trim(value)


WebChatMessageResponse = MessageResponse
WebChatMessageListResponse = MessageListResponse
