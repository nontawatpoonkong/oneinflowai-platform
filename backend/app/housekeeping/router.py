"""Workspace-scoped housekeeping endpoints."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.housekeeping import HousekeepingPriority, HousekeepingTaskStatus
from app.models.stay import RoomReadinessStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.housekeeping import (
    HousekeepingAssignRequest,
    RoomReadinessOverrideRequest,
)
from app.schemas.response import success_response
from app.services.housekeeping import HousekeepingService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


@router.get("/tasks")
async def list_tasks(
    property_id: uuid.UUID | None = None,
    room_id: uuid.UUID | None = None,
    task_status: HousekeepingTaskStatus | None = Query(default=None, alias="status"),
    assignee_id: uuid.UUID | None = None,
    priority: HousekeepingPriority | None = None,
    readiness_status: RoomReadinessStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await WorkspaceCapabilityService(session).require(
        workspace.id, user.id, WorkspaceCapability.HOUSEKEEPING_READ
    )
    data = await HousekeepingService(session).list_tasks(
        workspace.id,
        property_id=property_id,
        room_id=room_id,
        status=task_status,
        assignee_id=assignee_id,
        priority=priority,
        readiness_status=readiness_status,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump(mode="json"))


@router.post("/rooms/{room_id}/readiness-override")
async def override_room_readiness(
    room_id: uuid.UUID,
    payload: RoomReadinessOverrideRequest,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    data = await HousekeepingService(session).override_readiness(
        workspace.id,
        room_id,
        payload.readiness_status,
        payload.reason,
        user.id,
    )
    return success_response(data.model_dump(mode="json"))


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await WorkspaceCapabilityService(session).require(
        workspace.id, user.id, WorkspaceCapability.HOUSEKEEPING_READ
    )
    data = await HousekeepingService(session).get_task(workspace.id, task_id)
    return success_response(data.model_dump(mode="json"))


@router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: uuid.UUID,
    payload: HousekeepingAssignRequest,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    data = await HousekeepingService(session).assign(
        workspace.id, task_id, payload.assigned_to_user_id, user.id
    )
    return success_response(data.model_dump(mode="json"))


@router.post("/tasks/{task_id}/start")
async def start_task(
    task_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    data = await HousekeepingService(session).start(workspace.id, task_id, user.id)
    return success_response(data.model_dump(mode="json"))


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    data = await HousekeepingService(session).complete(workspace.id, task_id, user.id)
    return success_response(data.model_dump(mode="json"))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    data = await HousekeepingService(session).cancel(workspace.id, task_id, user.id)
    return success_response(data.model_dump(mode="json"))
