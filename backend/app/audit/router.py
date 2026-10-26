"""Read-only workspace audit endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.audit import AuditArea, AuditResult
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.audit import AuditEventPage, AuditEventResponse
from app.schemas.response import success_response
from app.services.audit import AuditService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


async def _authorized(user: User, workspace: Workspace, session: AsyncSession) -> None:
    await WorkspaceCapabilityService(session).require(
        workspace.id, user.id, WorkspaceCapability.AUDIT_READ
    )


@router.get("/events")
async def list_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    actor_user_id: uuid.UUID | None = None,
    action: str | None = Query(default=None, max_length=96),
    area: AuditArea | None = None,
    resource_type: str | None = Query(default=None, max_length=64),
    result: AuditResult | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    search: str | None = Query(default=None, min_length=2, max_length=80),
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    await _authorized(user, workspace, session)
    if any(
        value is not None and (value.tzinfo is None or value.utcoffset() is None)
        for value in (start_at, end_at)
    ):
        raise HTTPException(422, "Audit timestamps must include a timezone")
    if start_at and end_at and start_at >= end_at:
        raise HTTPException(422, "Audit range is invalid")
    data = await AuditService(session).list_events(
        workspace_id=workspace.id,
        page=page,
        page_size=page_size,
        actor_user_id=actor_user_id,
        action=action,
        area=area.value if area else None,
        resource_type=resource_type,
        result=result.value if result else None,
        start_at=start_at,
        end_at=end_at,
        search=search,
    )
    return success_response(AuditEventPage.model_validate(data).model_dump(mode="json"))


@router.get("/events/{event_id}")
async def get_event(
    event_id: uuid.UUID,
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    await _authorized(user, workspace, session)
    item = await AuditService(session).get_event(workspace.id, event_id)
    if item is None:
        raise HTTPException(404, "Audit event not found")
    return success_response(
        AuditEventResponse.model_validate(item).model_dump(mode="json")
    )
