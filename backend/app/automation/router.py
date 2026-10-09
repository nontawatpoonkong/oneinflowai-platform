"""Workspace-scoped automation management and execution observability."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.automation import (
    AutomationDefinitionCreate,
    AutomationDefinitionPatch,
    AutomationDefinitionResponse,
)
from app.schemas.response import success_response
from app.services.automation import AutomationService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()

STARTER_PRESETS = (
    {
        "key": "booking-confirmation",
        "trigger_event_type": "hotel.booking.confirmed",
        "schedule_mode": "IMMEDIATE",
        "action_type": "customer.message",
    },
    {
        "key": "pre-arrival",
        "trigger_event_type": "hotel.booking.confirmed",
        "schedule_mode": "BEFORE_DATE_FIELD",
        "action_type": "customer.message",
    },
    {
        "key": "payment-review-alert",
        "trigger_event_type": "hotel.payment.requires_review",
        "schedule_mode": "IMMEDIATE",
        "action_type": "internal.notification",
    },
    {
        "key": "post-stay",
        "trigger_event_type": "hotel.stay.checked_out",
        "schedule_mode": "DELAY_AFTER_EVENT",
        "action_type": "customer.message",
    },
)


async def _authorize(session, workspace_id, user_id, capability):
    await WorkspaceCapabilityService(session).require(workspace_id, user_id, capability)


@router.post("/validate")
async def validate_automation(
    payload: AutomationDefinitionCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_MANAGE
    )
    return success_response(AutomationService.validate(payload))


@router.get("")
async def list_automations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_READ
    )
    return success_response(
        await AutomationService(session).list(
            workspace.id, page=page, page_size=page_size
        )
    )


@router.get("/presets")
async def list_presets(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_READ
    )
    return success_response(list(STARTER_PRESETS))


@router.post("")
async def create_automation(
    payload: AutomationDefinitionCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_MANAGE
    )
    result = await AutomationService(session).create(workspace.id, user.id, payload)
    return success_response(result.model_dump(mode="json"))


@router.patch("/{automation_id}")
async def update_automation(
    automation_id: uuid.UUID,
    payload: AutomationDefinitionPatch,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_MANAGE
    )
    result = await AutomationService(session).update(
        workspace.id, automation_id, payload
    )
    return success_response(result.model_dump(mode="json"))


@router.post("/{automation_id}/enable")
async def enable_automation(
    automation_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_MANAGE
    )
    result = await AutomationService(session).set_active(
        workspace.id, automation_id, True
    )
    return success_response(result.model_dump(mode="json"))


@router.post("/{automation_id}/disable")
async def disable_automation(
    automation_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_MANAGE
    )
    result = await AutomationService(session).set_active(
        workspace.id, automation_id, False
    )
    return success_response(result.model_dump(mode="json"))


@router.get("/executions")
async def list_executions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_READ
    )
    return success_response(
        await AutomationService(session).list_executions(
            workspace.id, page=page, page_size=page_size
        )
    )


@router.get("/status")
async def automation_status(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_MANAGE
    )
    return success_response(
        await AutomationService(session).operational_status(workspace.id)
    )


@router.post("/executions/{execution_id}/retry")
async def retry_execution(
    execution_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_MANAGE
    )
    result = await AutomationService(session).retry_failed_execution(
        workspace.id, execution_id
    )
    return success_response(result.model_dump(mode="json"))


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_READ
    )
    result = await AutomationService(session).get_execution(workspace.id, execution_id)
    return success_response(result.model_dump(mode="json"))


@router.get("/{automation_id}")
async def get_automation(
    automation_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(
        session, workspace.id, user.id, WorkspaceCapability.AUTOMATION_READ
    )
    item = await AutomationService(session).get(workspace.id, automation_id)
    result = AutomationDefinitionResponse.model_validate(item)
    return success_response(result.model_dump(mode="json"))
