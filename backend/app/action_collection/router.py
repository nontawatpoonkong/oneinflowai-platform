"""Authenticated action collection routes."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.action.router import require_link_access
from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.integrations.action_extraction import create_action_field_extraction_provider
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.action import ActionResponse
from app.schemas.action_collection import (
    ActionCollectionConfirm,
    ActionCollectionCreate,
    ActionCollectionInput,
    ActionCollectionResponse,
    ActionCollectionResult,
)
from app.schemas.response import success_response
from app.services.action_collection import ActionCollectionService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import require_workspace_capability

router = APIRouter()

_action_read = require_workspace_capability(WorkspaceCapability.ACTION_READ)
_action_operate = require_workspace_capability(WorkspaceCapability.ACTION_OPERATE)


async def _collection_operator(
    workspace: Workspace = Depends(_action_operate),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Workspace:
    """Collection changes need action.operate and action.read.

    Every change returns the collected guest data and the confirmation summary
    that staff must review before confirming, so operators must also be allowed
    to read them. Both checks run before any provider call or write.
    """

    await WorkspaceCapabilityService(session).require(
        workspace.id, user.id, WorkspaceCapability.ACTION_READ
    )
    return workspace


def _service(session):
    return ActionCollectionService(session, create_action_field_extraction_provider())


def _result(service, collection, definition, *, token=None, action=None):
    complete = not collection.missing_fields and not collection.invalid_fields
    return ActionCollectionResult(
        session=ActionCollectionResponse.model_validate(collection),
        missing_field_metadata=service.missing_metadata(
            definition, collection.missing_fields
        ),
        confirmation_summary=service.summary(definition, collection.collected_payload)
        if complete
        else None,
        confirmation_token=token,
        next_step="ACTION_CREATED"
        if action
        else ("CONFIRM_ACTION" if complete else "COLLECT_MISSING_FIELDS"),
        action=ActionResponse.model_validate(action).model_dump(mode="json")
        if action
        else None,
    ).model_dump(mode="json")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: ActionCollectionCreate,
    workspace: Workspace = Depends(_collection_operator),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    _, capabilities = await WorkspaceCapabilityService(session).effective(
        workspace.id, user.id
    )
    require_link_access(
        capabilities,
        customer_id=payload.customer_id,
        conversation_id=payload.conversation_id,
    )
    service = _service(session)
    collection, definition, token = await service.create(workspace.id, payload)
    return success_response(
        _result(service, collection, definition, token=token),
        "Action collection created",
    )


@router.post("/{collection_id}/input")
async def add_collection_input(
    collection_id: uuid.UUID,
    payload: ActionCollectionInput,
    workspace: Workspace = Depends(_collection_operator),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    collection, definition, token = await service.add_input(
        workspace.id, collection_id, payload
    )
    return success_response(_result(service, collection, definition, token=token))


@router.get("/{collection_id}")
async def get_collection(
    collection_id: uuid.UUID,
    workspace: Workspace = Depends(_action_read),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    collection, definition = await service.get(workspace.id, collection_id)
    return success_response(_result(service, collection, definition))


@router.post("/{collection_id}/confirm")
async def confirm_collection(
    collection_id: uuid.UUID,
    payload: ActionCollectionConfirm,
    workspace: Workspace = Depends(_collection_operator),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    collection, definition, action = await service.confirm(
        workspace.id, user.id, collection_id, payload.confirmation_token
    )
    return success_response(
        _result(service, collection, definition, action=action),
        "Action confirmed and created",
    )


@router.post("/{collection_id}/cancel")
async def cancel_collection(
    collection_id: uuid.UUID,
    workspace: Workspace = Depends(_collection_operator),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    collection, definition = await service.cancel(workspace.id, collection_id)
    return success_response(_result(service, collection, definition))
