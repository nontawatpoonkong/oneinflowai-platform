"""Public demo chat contracts. No server-side session is created."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings


class DemoHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[DemoHistoryMessage] = Field(default_factory=list, max_length=8)
    preferred_language: Literal["th", "en"] | None = None

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, value: str) -> str:
        if len(value) > get_settings().DEMO_CHAT_MAX_INPUT_CHARS:
            raise ValueError("demo message exceeds configured maximum length")
        return value


class DemoCitation(BaseModel):
    label: str
    source: str


class DemoChatResponse(BaseModel):
    answer: str
    citations: list[DemoCitation]
