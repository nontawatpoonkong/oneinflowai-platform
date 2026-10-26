"""Workspace service.

Holds workspace-related business logic: slug generation and creating a
workspace together with its owner membership.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    SlugAlreadyExistsError,
    WorkspaceAccessDeniedError,
    WorkspaceNotFoundError,
)
from app.models.audit import AuditActorType, AuditArea
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.repositories.workspace import WorkspaceRepository
from app.repositories.workspace_member import WorkspaceMemberRepository
from app.services.audit import AuditService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.services.workspace_lifecycle import require_workspace_active
from app.utils.slug import RESERVED_SLUGS, generate_unique_slug, slugify


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspaces = WorkspaceRepository(session)
        self.members = WorkspaceMemberRepository(session)

    async def build_with_owner(
        self, *, owner_id: uuid.UUID, name: str, slug_source: str | None = None
    ) -> Workspace:
        """Create a workspace and its owner membership (flush, no commit).

        ``name`` is the display name; ``slug_source`` seeds the canonical slug
        and defaults to ``name`` when not provided (e.g. explicit creation).
        """
        slug = await generate_unique_slug(
            slug_source or name, self.workspaces.slug_exists
        )
        workspace = Workspace(name=name, slug=slug, owner_id=owner_id)
        await self.workspaces.add(workspace)

        membership = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=owner_id,
            role=WorkspaceRole.OWNER,
        )
        await self.members.add(membership)
        AuditService(self.session).record(
            workspace_id=workspace.id,
            actor_user_id=owner_id,
            actor_type=AuditActorType.USER,
            action="WORKSPACE_CREATED",
            area=AuditArea.WORKSPACE,
            resource_type="Workspace",
            resource_id=workspace.id,
        )
        return workspace

    async def get_primary_workspace(self, user_id: uuid.UUID) -> Workspace:
        workspace = await self.workspaces.get_primary_for_user(user_id)
        if workspace is None:
            raise WorkspaceNotFoundError("No workspace found for this user")
        return workspace

    async def get_by_slug(self, slug: str) -> Workspace:
        workspace = await self.workspaces.get_by_slug(slug)
        if workspace is None:
            raise WorkspaceNotFoundError()
        return workspace

    async def list_for_user(self, user_id: uuid.UUID) -> list[Workspace]:
        return await self.workspaces.list_for_user(user_id)

    async def list_members(
        self, workspace_id: uuid.UUID, requester_id: uuid.UUID
    ) -> list[WorkspaceMember]:
        workspace = await self.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError()
        await WorkspaceCapabilityService(self.session).require(
            workspace_id,
            requester_id,
            WorkspaceCapability.WORKSPACE_MEMBERS_READ,
        )
        return await self.members.list_for_workspace(workspace_id)

    async def update_workspace(
        self, workspace_id: uuid.UUID, requester_id: uuid.UUID, name: str
    ) -> Workspace:
        workspace = await self.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError()
        await WorkspaceCapabilityService(self.session).require(
            workspace_id,
            requester_id,
            WorkspaceCapability.WORKSPACE_SETTINGS_MANAGE,
        )

        if name != workspace.name:
            new_slug = slugify(name)
            if new_slug != workspace.slug:
                is_reserved = new_slug in RESERVED_SLUGS
                is_taken = is_reserved or await self.workspaces.slug_exists(
                    new_slug, exclude_id=workspace.id
                )
                if is_taken:
                    raise SlugAlreadyExistsError()
                workspace.slug = new_slug
            workspace.name = name
            AuditService(self.session).record(
                workspace_id=workspace.id,
                actor_user_id=requester_id,
                actor_type=AuditActorType.USER,
                action="WORKSPACE_SETTINGS_UPDATED",
                area=AuditArea.WORKSPACE,
                resource_type="Workspace",
                resource_id=workspace.id,
                metadata={"changed_fields": ["name", "slug"]},
            )
            await self.session.commit()
            await self.session.refresh(workspace)

        return workspace

    async def get_ai_instructions(
        self, workspace_id: uuid.UUID, requester_id: uuid.UUID
    ) -> str | None:
        workspace = await self.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError()
        await require_workspace_active(self.session, workspace_id)
        if await self.members.get_membership(workspace_id, requester_id) is None:
            raise WorkspaceNotFoundError()
        return workspace.ai_instructions

    async def update_ai_instructions(
        self,
        workspace_id: uuid.UUID,
        requester_id: uuid.UUID,
        instructions: str | None,
    ) -> str | None:
        workspace = await self.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError()
        await require_workspace_active(self.session, workspace_id)
        membership = await self.members.get_membership(workspace_id, requester_id)
        if membership is None:
            raise WorkspaceNotFoundError()
        if membership.role not in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
            raise WorkspaceAccessDeniedError(
                "Only workspace owners and admins can update AI instructions"
            )
        workspace.ai_instructions = instructions
        AuditService(self.session).record(
            workspace_id=workspace.id,
            actor_user_id=requester_id,
            actor_type=AuditActorType.USER,
            action="WORKSPACE_SETTINGS_UPDATED",
            area=AuditArea.SETTINGS,
            resource_type="Workspace",
            resource_id=workspace.id,
            metadata={"changed_fields": ["ai_instructions"]},
        )
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace.ai_instructions
