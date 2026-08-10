"""Authenticated in-app notification endpoints."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.notification import NotificationListResponse, NotificationResponse
from app.schemas.response import success_response
from app.services.notification import NotificationService
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


@router.get("")
async def list_notifications(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    items, unread = await NotificationService(session).list(workspace.id, user.id)
    data = NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        unread_count=unread,
    )
    return success_response(data.model_dump(mode="json"))


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    item = await NotificationService(session).mark_read(
        workspace.id, user.id, notification_id
    )
    return success_response(
        NotificationResponse.model_validate(item).model_dump(mode="json")
    )


@router.post("/read-all")
async def mark_all_notifications_read(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    count = await NotificationService(session).mark_all_read(workspace.id, user.id)
    return success_response({"marked_read": count})
