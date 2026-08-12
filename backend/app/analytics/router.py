"""Authenticated management analytics endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.analytics import AnalyticsOverview
from app.schemas.response import success_response
from app.services.analytics import AnalyticsService
from app.services.entitlement import ANALYTICS_BASIC, EntitlementService
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


@router.get("/overview")
async def overview(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=30)
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "Analytics range must include a timezone")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if start >= end or end - start > timedelta(days=366):
        raise HTTPException(422, "Analytics range is invalid")
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if member is None or member.role not in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
        raise HTTPException(403, "Analytics access requires workspace management")
    await EntitlementService(session).require(workspace.id, ANALYTICS_BASIC)
    data = await AnalyticsService(session).overview(workspace.id, start, end)
    return success_response(
        AnalyticsOverview.model_validate(data).model_dump(mode="json")
    )
