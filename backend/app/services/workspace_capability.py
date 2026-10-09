"""Small role-to-capability policy for workspace operations."""

import enum
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import WorkspaceAccessDeniedError
from app.models.workspace_member import WorkspaceMember, WorkspaceRole


class WorkspaceCapability(enum.StrEnum):
    AUTOMATION_READ = "automation.read"
    AUTOMATION_MANAGE = "automation.manage"
    HOTEL_HOUSEKEEPING_OPERATE = "hotel.housekeeping.operate"
    HOTEL_HOUSEKEEPING_MANAGE = "hotel.housekeeping.manage"
    HOTEL_READINESS_OVERRIDE = "hotel.readiness.override"


_ROLE_CAPABILITIES = {
    WorkspaceRole.OWNER: frozenset(WorkspaceCapability),
    WorkspaceRole.ADMIN: frozenset(WorkspaceCapability),
    WorkspaceRole.MEMBER: frozenset(
        {
            WorkspaceCapability.AUTOMATION_READ,
            WorkspaceCapability.HOTEL_HOUSEKEEPING_OPERATE,
        }
    ),
}


class WorkspaceCapabilityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def membership(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember:
        member = await self.session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if member is None:
            raise WorkspaceAccessDeniedError("Workspace membership required")
        return member

    async def require(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        capability: WorkspaceCapability,
    ) -> WorkspaceMember:
        member = await self.membership(workspace_id, user_id)
        if capability not in _ROLE_CAPABILITIES[member.role]:
            raise WorkspaceAccessDeniedError(
                f"Workspace capability required: {capability.value}"
            )
        return member

    @staticmethod
    def role_has(role: WorkspaceRole, capability: WorkspaceCapability) -> bool:
        return capability in _ROLE_CAPABILITIES[role]
