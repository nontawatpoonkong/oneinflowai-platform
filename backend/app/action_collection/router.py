"""Authenticated action collection routes."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


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
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
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
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    collection, definition = await service.get(workspace.id, collection_id)
    return success_response(_result(service, collection, definition))


@router.post("/{collection_id}/confirm")
async def confirm_collection(
    collection_id: uuid.UUID,
    payload: ActionCollectionConfirm,
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    collection, definition = await service.cancel(workspace.id, collection_id)
    return success_response(_result(service, collection, definition))
