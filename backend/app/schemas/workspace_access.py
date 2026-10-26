"""Workspace access lifecycle and granular permission API contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.workspace_access import WorkspaceAccessRequestStatus
from app.models.workspace_member import WorkspaceRole


class JoinCodeResolveRequest(BaseModel):
    code: str = Field(min_length=8, max_length=40)


class JoinCodeWorkspaceResponse(BaseModel):
    name: str


class AccessRequestCreate(BaseModel):
    code: str = Field(min_length=8, max_length=40)
    message: str | None = Field(default=None, max_length=500)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AccessRequestResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str | None = None
    user_id: uuid.UUID
    email: EmailStr | None = None
    full_name: str | None = None
    status: WorkspaceAccessRequestStatus
    message: str | None
    requested_at: datetime
    reviewed_at: datetime | None
    reviewed_by_user_id: uuid.UUID | None
    rejection_reason: str | None


class AccessRequestApprove(BaseModel):
    role: WorkspaceRole = WorkspaceRole.MEMBER
    capabilities: list[str] = Field(default_factory=list, max_length=64)


class AccessRequestReject(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class JoinSettingsUpdate(BaseModel):
    join_enabled: bool


class JoinSettingsResponse(BaseModel):
    join_enabled: bool
    code_hint: str | None
    join_code: str | None = None


class MemberRoleUpdate(BaseModel):
    role: WorkspaceRole


class MemberCapabilitiesUpdate(BaseModel):
    capabilities: list[str] = Field(default_factory=list, max_length=64)


class WorkspaceAccessResponse(BaseModel):
    workspace_id: uuid.UUID
    membership_id: uuid.UUID
    role: WorkspaceRole
    capabilities: list[str]


class CapabilityRegistryResponse(BaseModel):
    capabilities: list[str]
