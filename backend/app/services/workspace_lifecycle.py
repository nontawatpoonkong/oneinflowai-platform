"""Central enforcement for the platform-controlled Workspace lifecycle."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import WorkspaceSuspendedError
from app.models.workspace import Workspace, WorkspaceStatus


async def require_workspace_active(
    session: AsyncSession, workspace_id: uuid.UUID
) -> Workspace:
    """Fail closed before an operational or public Workspace action."""

    workspace = await session.get(Workspace, workspace_id)
    if workspace is None or workspace.status != WorkspaceStatus.ACTIVE.value:
        raise WorkspaceSuspendedError()
    return workspace
