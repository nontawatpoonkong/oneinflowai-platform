"""Workspace resolution dependencies."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core import context
from app.core.exceptions import WorkspaceAccessDeniedError
from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.services.workspace import WorkspaceService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.services.workspace_lifecycle import require_workspace_active


async def get_current_workspace(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-ID"),
) -> Workspace:
    """Resolve the authenticated user's active (primary) workspace.

    Customer operations are scoped to this workspace, enforcing isolation.
    Also populates the workspace_id logging context.
    """
    service = WorkspaceService(session)
    if x_workspace_id:
        try:
            workspace_id = uuid.UUID(x_workspace_id)
        except ValueError:
            raise WorkspaceAccessDeniedError("Invalid workspace context") from None
        await WorkspaceCapabilityService(session).membership(workspace_id, user.id)
        workspace = await service.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceAccessDeniedError("Invalid workspace context")
    else:
        workspace = await service.get_primary_workspace(user.id)
    await require_workspace_active(session, workspace.id)
    context.set_workspace_id(str(workspace.id))
    return workspace


def require_workspace_capability(
    capability: WorkspaceCapability,
) -> Callable[..., Workspace]:
    """Return a dependency that resolves Workspace and enforces one capability."""

    async def dependency(
        workspace: Annotated[Workspace, Depends(get_current_workspace)],
        user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> Workspace:
        await WorkspaceCapabilityService(session).require(
            workspace.id, user.id, capability
        )
        return workspace

    return dependency
