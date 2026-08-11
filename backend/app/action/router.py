"""Authenticated workspace-scoped action queue routes."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.action import ActionPriority, ActionRequestStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.action import (
    ActionAssign,
    ActionCreate,
    ActionDefinitionCreate,
    ActionDefinitionResponse,
    ActionDefinitionUpdate,
    ActionListResponse,
    ActionResponse,
)
from app.schemas.response import success_response
from app.services.action import ActionService
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


def _definition(value):
    return ActionDefinitionResponse.model_validate(value).model_dump(mode="json")


def _action(value):
    return ActionResponse.model_validate(value).model_dump(mode="json")


@router.post("/definitions", status_code=status.HTTP_201_CREATED)
async def create_definition(
    payload: ActionDefinitionCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = ActionService(session)
    await service.require_definition_admin(workspace.id, user.id)
    return success_response(
        _definition(await service.create_definition(workspace.id, payload)),
        "Action definition created",
    )


@router.get("/definitions")
async def list_definitions(
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    items = await ActionService(session).list_definitions(workspace.id)
    return success_response([_definition(item) for item in items])


@router.get("/definitions/{definition_id}")
async def get_definition(
    definition_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _definition(
            await ActionService(session).get_definition(workspace.id, definition_id)
        )
    )


@router.patch("/definitions/{definition_id}")
async def update_definition(
    definition_id: uuid.UUID,
    payload: ActionDefinitionUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = ActionService(session)
    await service.require_definition_admin(workspace.id, user.id)
    return success_response(
        _definition(
            await service.update_definition(workspace.id, definition_id, payload)
        )
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_action(
    payload: ActionCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _action(await ActionService(session).create(workspace.id, user.id, payload)),
        "Action created",
    )


@router.get("")
async def list_actions(
    status_filter: ActionRequestStatus | None = Query(None, alias="status"),
    priority: ActionPriority | None = None,
    assigned_to: uuid.UUID | None = None,
    action_definition_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    items, total = await ActionService(session).list(
        workspace.id,
        status=status_filter,
        priority=priority,
        assigned_to=assigned_to,
        action_definition_id=action_definition_id,
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
    )
    data = ActionListResponse(
        items=[ActionResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )
    return success_response(data.model_dump(mode="json"))


@router.get("/{action_id}")
async def get_action(
    action_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _action(await ActionService(session).get(workspace.id, action_id))
    )


@router.post("/{action_id}/assign")
async def assign_action(
    action_id: uuid.UUID,
    payload: ActionAssign,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _action(
            await ActionService(session).assign(
                workspace.id, action_id, payload.user_id, user.id
            )
        )
    )


async def _transition(action_id, target, workspace, user, session):
    return success_response(
        _action(
            await ActionService(session).transition(
                workspace.id, action_id, target, user.id
            )
        )
    )


@router.post("/{action_id}/start")
async def start_action(
    action_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _transition(
        action_id, ActionRequestStatus.IN_PROGRESS, workspace, user, session
    )


@router.post("/{action_id}/complete")
async def complete_action(
    action_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _transition(
        action_id, ActionRequestStatus.COMPLETED, workspace, user, session
    )


@router.post("/{action_id}/fail")
async def fail_action(
    action_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _transition(
        action_id, ActionRequestStatus.FAILED, workspace, user, session
    )


@router.post("/{action_id}/cancel")
async def cancel_action(
    action_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _transition(
        action_id, ActionRequestStatus.CANCELLED, workspace, user, session
    )
