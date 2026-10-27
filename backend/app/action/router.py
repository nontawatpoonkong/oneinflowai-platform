"""Authenticated workspace-scoped action queue routes."""

import uuid
from typing import NamedTuple

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.exceptions import WorkspaceAccessDeniedError
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
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import (
    get_current_workspace,
    require_workspace_capability,
)

router = APIRouter()

# action.read covers Actions and Action Definitions; action.operate covers
# creating Actions and every state change. Definition changes stay
# OWNER/ADMIN-only through ActionService.require_definition_admin.
_action_read = require_workspace_capability(WorkspaceCapability.ACTION_READ)
_action_operate = require_workspace_capability(WorkspaceCapability.ACTION_OPERATE)

# Guest-linked fields that only callers holding action.read may receive.
_GUEST_FIELDS = ("payload", "customer_id", "conversation_id", "idempotency_key")


class _Operator(NamedTuple):
    workspace: Workspace
    user: User
    capabilities: frozenset[WorkspaceCapability]

    @property
    def details_visible(self) -> bool:
        return WorkspaceCapability.ACTION_READ in self.capabilities


def require_link_access(
    capabilities: frozenset[WorkspaceCapability],
    *,
    customer_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
) -> None:
    """Linking a guest record needs the right to read it.

    Checked before the id is looked up, so callers without access learn
    nothing about whether the customer or conversation exists.
    """

    for value, capability in (
        (customer_id, WorkspaceCapability.GUEST_READ),
        (conversation_id, WorkspaceCapability.CONVERSATION_READ),
    ):
        if value is not None and capability not in capabilities:
            raise WorkspaceAccessDeniedError(
                f"Workspace capability required: {capability.value}"
            )


async def _operator(
    workspace: Workspace = Depends(_action_operate),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> _Operator:
    """Resolve an action.operate caller and whether it may see guest data."""

    _, capabilities = await WorkspaceCapabilityService(session).effective(
        workspace.id, user.id
    )
    return _Operator(workspace, user, capabilities)


def _definition(value):
    return ActionDefinitionResponse.model_validate(value).model_dump(mode="json")


def _action(value, *, details_visible: bool = True):
    data = ActionResponse.model_validate(value).model_dump(mode="json")
    if not details_visible:
        # Operators without action.read get the outcome of their change, never
        # the guest data the Action carries.
        for key in _GUEST_FIELDS:
            data.pop(key)
    data["details_visible"] = details_visible
    return data


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
        _definition(
            await service.create_definition(
                workspace.id, payload, actor_user_id=user.id
            )
        ),
        "Action definition created",
    )


@router.get("/definitions")
async def list_definitions(
    workspace: Workspace = Depends(_action_read),
    session: AsyncSession = Depends(get_db),
):
    items = await ActionService(session).list_definitions(workspace.id)
    return success_response([_definition(item) for item in items])


@router.get("/definitions/{definition_id}")
async def get_definition(
    definition_id: uuid.UUID,
    workspace: Workspace = Depends(_action_read),
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
            await service.update_definition(
                workspace.id, definition_id, payload, actor_user_id=user.id
            )
        )
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_action(
    payload: ActionCreate,
    operator: _Operator = Depends(_operator),
    session: AsyncSession = Depends(get_db),
):
    require_link_access(
        operator.capabilities,
        customer_id=payload.customer_id,
        conversation_id=payload.conversation_id,
    )
    action = await ActionService(session).create(
        operator.workspace.id, operator.user.id, payload
    )
    return success_response(
        _action(action, details_visible=operator.details_visible), "Action created"
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
    workspace: Workspace = Depends(_action_read),
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
    workspace: Workspace = Depends(_action_read),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _action(await ActionService(session).get(workspace.id, action_id))
    )


@router.post("/{action_id}/assign")
async def assign_action(
    action_id: uuid.UUID,
    payload: ActionAssign,
    operator: _Operator = Depends(_operator),
    session: AsyncSession = Depends(get_db),
):
    action = await ActionService(session).assign(
        operator.workspace.id, action_id, payload.user_id, operator.user.id
    )
    return success_response(_action(action, details_visible=operator.details_visible))


async def _transition(action_id, target, operator: _Operator, session):
    action = await ActionService(session).transition(
        operator.workspace.id, action_id, target, operator.user.id
    )
    return success_response(_action(action, details_visible=operator.details_visible))


@router.post("/{action_id}/start")
async def start_action(
    action_id: uuid.UUID,
    operator: _Operator = Depends(_operator),
    session: AsyncSession = Depends(get_db),
):
    return await _transition(
        action_id, ActionRequestStatus.IN_PROGRESS, operator, session
    )


@router.post("/{action_id}/complete")
async def complete_action(
    action_id: uuid.UUID,
    operator: _Operator = Depends(_operator),
    session: AsyncSession = Depends(get_db),
):
    return await _transition(
        action_id, ActionRequestStatus.COMPLETED, operator, session
    )


@router.post("/{action_id}/fail")
async def fail_action(
    action_id: uuid.UUID,
    operator: _Operator = Depends(_operator),
    session: AsyncSession = Depends(get_db),
):
    return await _transition(action_id, ActionRequestStatus.FAILED, operator, session)


@router.post("/{action_id}/cancel")
async def cancel_action(
    action_id: uuid.UUID,
    operator: _Operator = Depends(_operator),
    session: AsyncSession = Depends(get_db),
):
    return await _transition(
        action_id, ActionRequestStatus.CANCELLED, operator, session
    )
