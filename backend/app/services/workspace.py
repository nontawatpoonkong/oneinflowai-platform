"""Workspace service.

Holds workspace-related business logic: slug generation and creating a
workspace together with its owner membership.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.repositories.workspace import WorkspaceRepository
from app.repositories.workspace_member import WorkspaceMemberRepository
from app.utils.slug import generate_unique_slug


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
        return workspace

    async def create_workspace(self, *, owner_id: uuid.UUID, name: str) -> Workspace:
        """Public unit of work: create workspace + owner membership, commit."""
        workspace = await self.build_with_owner(owner_id=owner_id, name=name)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace
