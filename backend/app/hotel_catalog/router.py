"""Workspace-scoped rich room catalog and availability calendar endpoints."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.hotel_catalog import RoomImageCategory
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.hotel_catalog import (
    RichRoomTypeCreate,
    RoomTypeAmenityInput,
    RoomTypeBedInput,
    RoomTypeImageCreate,
    RoomTypeImageOrderItem,
)
from app.schemas.response import success_response
from app.services.hotel_catalog import (
    AvailabilityCalendarService,
    RichHotelCatalogService,
)
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


async def _require(session, workspace, user, capability):
    await WorkspaceCapabilityService(session).require(workspace.id, user.id, capability)


@router.get("/catalog/amenities")
async def list_amenities(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_READ)
    values = await RichHotelCatalogService(session).ensure_amenity_registry()
    await session.commit()
    return success_response(
        [
            {
                "id": str(item.id),
                "code": item.code,
                "category": item.category,
                "default_name_en": item.default_name_en,
                "default_name_th": item.default_name_th,
                "value_type": item.value_type,
                "active": item.active,
                "sort_order": item.sort_order,
            }
            for item in values
        ]
    )


@router.post("/catalog/room-types", status_code=status.HTTP_201_CREATED)
async def create_rich_room_type(
    payload: RichRoomTypeCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    value = await RichHotelCatalogService(session).create_rich_room_type(
        workspace.id, payload
    )
    return success_response(value.model_dump(mode="json"), "Room type created")


@router.get("/catalog/room-types/{room_type_id}")
async def room_type_detail(
    room_type_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_READ)
    value = await RichHotelCatalogService(session).detail(workspace.id, room_type_id)
    return success_response(value.model_dump(mode="json"))


@router.get("/catalog/room-types/{room_type_id}/customer-facts")
async def customer_room_facts(
    room_type_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_READ)
    value = await RichHotelCatalogService(session).customer_facts(
        workspace.id, room_type_id
    )
    return success_response(value.model_dump(mode="json"))


@router.put("/catalog/room-types/{room_type_id}/beds")
async def replace_beds(
    room_type_id: uuid.UUID,
    payload: list[RoomTypeBedInput],
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    values = await RichHotelCatalogService(session).replace_beds(
        workspace.id, room_type_id, payload
    )
    return success_response([item.model_dump(mode="json") for item in values])


@router.put("/catalog/room-types/{room_type_id}/amenities")
async def replace_amenities(
    room_type_id: uuid.UUID,
    payload: list[RoomTypeAmenityInput],
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    values = await RichHotelCatalogService(session).replace_amenities(
        workspace.id, room_type_id, payload
    )
    return success_response([item.model_dump(mode="json") for item in values])


@router.post(
    "/catalog/room-types/{room_type_id}/images", status_code=status.HTTP_201_CREATED
)
async def upload_image(
    room_type_id: uuid.UUID,
    file: UploadFile = File(...),
    alt_text: str = Form(...),
    caption: str | None = Form(default=None),
    image_category: RoomImageCategory = Form(default=RoomImageCategory.ROOM),
    sort_order: int = Form(default=0, ge=0, le=1000),
    is_cover: bool = Form(default=False),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    metadata = RoomTypeImageCreate(
        alt_text=alt_text,
        caption=caption,
        image_category=image_category,
        sort_order=sort_order,
        is_cover=is_cover,
    )
    value = await RichHotelCatalogService(session).add_image(
        workspace.id, room_type_id, metadata, await file.read(), file.content_type or ""
    )
    return success_response(value.model_dump(mode="json"), "Room image uploaded")


@router.get("/catalog/room-types/{room_type_id}/images/{image_id}/content")
async def image_content(
    room_type_id: uuid.UUID,
    image_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_READ)
    data, mime_type = await RichHotelCatalogService(session).image_content(
        workspace.id, room_type_id, image_id
    )
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.put("/catalog/room-types/{room_type_id}/images/order")
async def reorder_images(
    room_type_id: uuid.UUID,
    payload: list[RoomTypeImageOrderItem],
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    values = await RichHotelCatalogService(session).reorder_images(
        workspace.id, room_type_id, payload
    )
    return success_response([item.model_dump(mode="json") for item in values])


@router.get("/availability-calendar")
async def availability_calendar(
    property_id: uuid.UUID,
    start_date: date,
    days: int = Query(default=7),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_READ)
    value = await AvailabilityCalendarService(session).calendar(
        workspace.id, property_id, start_date, days
    )
    return success_response(value.model_dump(mode="json"))
