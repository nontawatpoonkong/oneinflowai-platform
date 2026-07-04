"""Workspace resolution dependencies."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core import context
from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.services.workspace import WorkspaceService


async def get_current_workspace(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Workspace:
    """Resolve the authenticated user's active (primary) workspace.

    Customer operations are scoped to this workspace, enforcing isolation.
    Also populates the workspace_id logging context.
    """
    workspace = await WorkspaceService(session).get_primary_workspace(user.id)
    context.set_workspace_id(str(workspace.id))
    return workspace
