"""Workspace-scoped Guest CRM and Customer 360 endpoints."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.crm import (
    CustomerNoteCreate,
    CustomerNoteResponse,
    CustomerPreferenceResponse,
    CustomerPreferenceUpdate,
    CustomerPreferenceWrite,
    CustomerTagCreate,
    CustomerTagResponse,
)
from app.schemas.response import success_response
from app.services.crm import Customer360Service
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


@router.get("/customers")
async def list_crm_customers(
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, max_length=200),
    tag_id: uuid.UUID | None = None,
    has_active_booking: bool | None = None,
    has_payment_exception: bool | None = None,
    repeat_guest: bool | None = None,
    needs_attention: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    data = await Customer360Service(session).list_customers(
        workspace.id,
        search=q,
        tag_id=tag_id,
        has_active_booking=has_active_booking,
        has_payment_exception=has_payment_exception,
        repeat_guest=repeat_guest,
        needs_attention=needs_attention,
        page=page,
        page_size=page_size,
    )
    return success_response(data=data.model_dump(mode="json"))


@router.get("/customers/{customer_id}")
async def get_customer_360(
    customer_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
):
    data = await Customer360Service(session).get_customer_360(
        workspace.id, customer_id, user.id, limit=limit
    )
    return success_response(data=data.model_dump(mode="json"))


@router.get("/customers/{customer_id}/timeline")
async def get_customer_timeline(
    customer_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1, le=20),
    page_size: int = Query(default=20, ge=1, le=50),
):
    data = await Customer360Service(session).timeline(
        workspace.id, customer_id, user.id, page=page, page_size=page_size
    )
    return success_response(data=data.model_dump(mode="json"))


@router.post("/customers/{customer_id}/notes", status_code=status.HTTP_201_CREATED)
async def add_customer_note(
    customer_id: uuid.UUID,
    payload: CustomerNoteCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    note = await Customer360Service(session).add_note(
        workspace.id, customer_id, user.id, payload
    )
    return success_response(
        data=CustomerNoteResponse.model_validate(note).model_dump(mode="json")
    )


@router.post(
    "/customers/{customer_id}/preferences", status_code=status.HTTP_201_CREATED
)
async def set_customer_preference(
    customer_id: uuid.UUID,
    payload: CustomerPreferenceWrite,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    preference = await Customer360Service(session).set_preference(
        workspace.id, customer_id, user.id, payload
    )
    return success_response(
        data=CustomerPreferenceResponse.model_validate(preference).model_dump(
            mode="json"
        )
    )


@router.patch("/customers/{customer_id}/preferences/{preference_id}")
async def update_customer_preference(
    customer_id: uuid.UUID,
    preference_id: uuid.UUID,
    payload: CustomerPreferenceUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    preference = await Customer360Service(session).update_preference(
        workspace.id, customer_id, preference_id, user.id, payload
    )
    return success_response(
        data=CustomerPreferenceResponse.model_validate(preference).model_dump(
            mode="json"
        )
    )


@router.get("/tags")
async def list_crm_tags(
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    tags = await Customer360Service(session).list_tags(workspace.id)
    return success_response(
        data=[
            CustomerTagResponse.model_validate(tag).model_dump(mode="json")
            for tag in tags
        ]
    )


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_crm_tag(
    payload: CustomerTagCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    tag = await Customer360Service(session).create_tag(workspace.id, user.id, payload)
    return success_response(
        data=CustomerTagResponse.model_validate(tag).model_dump(mode="json")
    )


@router.post("/customers/{customer_id}/tags/{tag_id}")
async def assign_customer_tag(
    customer_id: uuid.UUID,
    tag_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    tag = await Customer360Service(session).assign_tag(
        workspace.id, customer_id, tag_id, user.id
    )
    return success_response(
        data=CustomerTagResponse.model_validate(tag).model_dump(mode="json")
    )


@router.delete("/customers/{customer_id}/tags/{tag_id}")
async def remove_customer_tag(
    customer_id: uuid.UUID,
    tag_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await Customer360Service(session).remove_tag(
        workspace.id, customer_id, tag_id, user.id
    )
    return success_response(data={"id": str(tag_id)})
