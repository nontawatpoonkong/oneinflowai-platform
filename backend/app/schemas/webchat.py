"""Public WebChat request/response schemas."""

import enum
import uuid
from typing import Any

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
    client_message_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value: object) -> object:
        return _trim(value)


WebChatMessageResponse = MessageResponse
WebChatMessageListResponse = MessageListResponse


class WebChatResponseType(enum.StrEnum):
    ANSWER = "ANSWER"
    ACTION_COLLECTING = "ACTION_COLLECTING"
    ACTION_CONFIRMATION = "ACTION_CONFIRMATION"
    ACTION_CREATED = "ACTION_CREATED"
    ACTION_CANCELLED = "ACTION_CANCELLED"
    AI_TOOL_CONFIRMATION = "AI_TOOL_CONFIRMATION"
    AI_TOOL_RESULT = "AI_TOOL_RESULT"
    AI_TOOL_CANCELLED = "AI_TOOL_CANCELLED"
    HUMAN_MODE = "HUMAN_MODE"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    NO_RESPONSE = "NO_RESPONSE"
    ERROR = "ERROR"


class WebChatActionDecision(BaseModel):
    client_message_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )
    confirmation_token: str | None = Field(default=None, min_length=32, max_length=512)


class WebChatAssistantResponse(BaseModel):
    type: WebChatResponseType
    message: str | None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    action_collection: dict[str, Any] | None = None
    action_request_id: uuid.UUID | None = None
    ai_tool_action: dict[str, Any] | None = None


class WebChatAIResponse(BaseModel):
    conversation_id: uuid.UUID
    customer_message: MessageResponse
    assistant: WebChatAssistantResponse | None
