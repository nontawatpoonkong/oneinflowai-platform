"""Workspace-scoped physical-room and Stay operations endpoints."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.stay import (
    RoomOperationalStatus,
    RoomReadinessStatus,
    StayStatus,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.response import success_response
from app.schemas.stay import (
    CheckInRequest,
    RoomAssignmentRequest,
    RoomCreate,
    RoomUpdate,
)
from app.services.stay import StayOperationsService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


async def _require(session, workspace, user, capability):
    await WorkspaceCapabilityService(session).require(workspace.id, user.id, capability)


@router.get("/rooms")
async def list_rooms(
    property_id: uuid.UUID | None = None,
    room_type_id: uuid.UUID | None = None,
    floor: str | None = Query(default=None, max_length=32),
    building: str | None = Query(default=None, max_length=80),
    wing: str | None = Query(default=None, max_length=80),
    operational_status: RoomOperationalStatus | None = None,
    readiness_status: RoomReadinessStatus | None = None,
    active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_READ)
    data = await StayOperationsService(session).list_rooms(
        workspace.id,
        property_id=property_id,
        room_type_id=room_type_id,
        floor=floor,
        building=building,
        wing=wing,
        operational_status=operational_status,
        readiness_status=readiness_status,
        active=active,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump(mode="json"))


@router.post("/rooms", status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    data = await service.create_room(workspace.id, payload)
    return success_response(data.model_dump(mode="json"), "Room created")


@router.get("/rooms/{room_id}")
async def get_room(
    room_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.ROOM_READ)
    data = await StayOperationsService(session).get_room(workspace.id, room_id)
    return success_response(data.model_dump(mode="json"))


@router.patch("/rooms/{room_id}")
async def update_room(
    room_id: uuid.UUID,
    payload: RoomUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    data = await service.update_room(workspace.id, room_id, payload)
    return success_response(data.model_dump(mode="json"))


@router.post("/rooms/{room_id}/out-of-service")
async def set_room_out_of_service(
    room_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    data = await service.set_room_out_of_service(workspace.id, room_id)
    return success_response(data.model_dump(mode="json"))


@router.post("/rooms/{room_id}/available")
async def set_room_available(
    room_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.ROOM_MANAGE)
    data = await service.set_room_available(workspace.id, room_id)
    return success_response(data.model_dump(mode="json"))


@router.get("/stays")
async def list_stays(
    stay_status: StayStatus | None = Query(default=None, alias="status"),
    property_id: uuid.UUID | None = None,
    arrival_date: date | None = None,
    departure_date: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.STAY_READ)
    data = await StayOperationsService(session).list_stays(
        workspace.id,
        status=stay_status,
        property_id=property_id,
        arrival_date=arrival_date,
        departure_date=departure_date,
        page=page,
        page_size=page_size,
    )
    return success_response(data.model_dump(mode="json"))


@router.get("/stays/{stay_id}")
async def get_stay(
    stay_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.STAY_READ)
    data = await StayOperationsService(session).get_stay(workspace.id, stay_id)
    return success_response(data.model_dump(mode="json"))


@router.post("/bookings/{booking_id}/stay", status_code=status.HTTP_201_CREATED)
async def create_stay(
    booking_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.STAY_CHECKIN)
    data = await service.create_stay_from_booking(workspace.id, booking_id, user.id)
    return success_response(data.model_dump(mode="json"), "Stay created")


@router.post("/stays/{stay_id}/assign-room")
async def assign_rooms(
    stay_id: uuid.UUID,
    payload: RoomAssignmentRequest,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.STAY_CHECKIN)
    data = await service.assign_rooms(workspace.id, stay_id, payload.room_ids, user.id)
    return success_response(data.model_dump(mode="json"))


@router.post("/stays/{stay_id}/check-in")
async def check_in(
    stay_id: uuid.UUID,
    payload: CheckInRequest,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.STAY_CHECKIN)
    data = await service.check_in(
        workspace.id, stay_id, user.id, room_ids=payload.room_ids
    )
    return success_response(data.model_dump(mode="json"))


@router.post("/stays/{stay_id}/check-out")
async def check_out(
    stay_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.STAY_CHECKOUT)
    data = await service.check_out(workspace.id, stay_id, user.id)
    return success_response(data.model_dump(mode="json"))


@router.post("/stays/{stay_id}/no-show")
async def mark_no_show(
    stay_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = StayOperationsService(session)
    await _require(session, workspace, user, WorkspaceCapability.STAY_NO_SHOW)
    data = await service.mark_no_show(workspace.id, stay_id, user.id)
    return success_response(data.model_dump(mode="json"))
