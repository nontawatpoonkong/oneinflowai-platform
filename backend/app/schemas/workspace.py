"""Workspace schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.workspace_member import WorkspaceRole

_NAME_MAX_LENGTH = 100
AI_INSTRUCTIONS_MAX_LENGTH = 8_000


class WorkspaceCreateRequest(BaseModel):
    # Existing contract (unchanged): kept at max_length=255.
    name: str = Field(min_length=1, max_length=255)


class WorkspaceUpdateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Workspace name cannot be empty")
        if len(value) > _NAME_MAX_LENGTH:
            raise ValueError(
                f"Workspace name must be at most {_NAME_MAX_LENGTH} characters"
            )
        return value


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WorkspaceAIInstructionsUpdate(BaseModel):
    instructions: str | None = Field(
        default=None, max_length=AI_INSTRUCTIONS_MAX_LENGTH
    )

    @field_validator("instructions")
    @classmethod
    def normalize_instructions(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class WorkspaceAIInstructionsResponse(BaseModel):
    instructions: str | None
    max_length: int = AI_INSTRUCTIONS_MAX_LENGTH


class WorkspaceMemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: WorkspaceRole
    joined_at: datetime
