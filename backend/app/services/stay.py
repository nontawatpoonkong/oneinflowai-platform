"""Transactional physical-room and Stay operations."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.booking import Booking, BookingItem, BookingStatus
from app.models.hotel import Property, RoomType
from app.models.housekeeping import (
    HousekeepingEvent,
    HousekeepingEventType,
    HousekeepingPriority,
    HousekeepingTask,
    HousekeepingTaskStatus,
)
from app.models.stay import (
    HotelRoom,
    RoomOperationalStatus,
    RoomReadinessStatus,
    Stay,
    StayEvent,
    StayEventType,
    StayRoomAssignment,
    StayStatus,
)
from app.schemas.stay import (
    RoomCreate,
    RoomListResponse,
    RoomResponse,
    RoomUpdate,
    StayEventResponse,
    StayListResponse,
    StayResponse,
    StayRoomSummary,
)
from app.services.hotel import HotelCatalogService


class StayConflictError(AppError):
    status_code = 409
    code = "STAY_CONFLICT"
    message = "Stay operation conflicts with current operational state"


class StayTransitionError(AppError):
    status_code = 409
    code = "STAY_TRANSITION_INVALID"
    message = "Stay transition is not allowed"


class StayValidationError(AppError):
    status_code = 422
    code = "STAY_VALIDATION_ERROR"
    message = "Stay operation is invalid"


class StayOperationsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.catalog = HotelCatalogService(session)

    async def require_admin(self, workspace_id, user_id) -> None:
        await self.catalog.require_admin(workspace_id, user_id)

    async def create_room(
        self, workspace_id: uuid.UUID, data: RoomCreate
    ) -> RoomResponse:
        prop, room_type = await self._catalog_room_type(
            workspace_id, data.property_id, data.room_type_id
        )
        room = HotelRoom(
            workspace_id=workspace_id,
            property_id=prop.id,
            room_type_id=room_type.id,
            code=data.code,
            floor=data.floor,
            active=True,
            operational_status=RoomOperationalStatus.AVAILABLE,
            readiness_status=RoomReadinessStatus.READY,
        )
        self.session.add(room)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise StayConflictError(
                "Room code already exists in this property"
            ) from exc
        return await self.get_room(workspace_id, room.id)

    async def update_room(
        self, workspace_id: uuid.UUID, room_id: uuid.UUID, data: RoomUpdate
    ) -> RoomResponse:
        room = await self._room(workspace_id, room_id, lock=True)
        if data.active is False:
            await self._ensure_room_unassigned(room)
            if room.operational_status == RoomOperationalStatus.OCCUPIED:
                raise StayConflictError("An occupied room cannot be deactivated")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(room, field, value)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise StayConflictError(
                "Room code already exists in this property"
            ) from exc
        return await self.get_room(workspace_id, room_id)

    async def set_room_out_of_service(
        self, workspace_id: uuid.UUID, room_id: uuid.UUID
    ) -> RoomResponse:
        room = await self._room(workspace_id, room_id, lock=True)
        if room.operational_status == RoomOperationalStatus.OCCUPIED:
            raise StayConflictError("An occupied room cannot be put out of service")
        await self._ensure_room_unassigned(room)
        room.operational_status = RoomOperationalStatus.OUT_OF_SERVICE
        await self.session.commit()
        return await self.get_room(workspace_id, room_id)

    async def set_room_available(
        self, workspace_id: uuid.UUID, room_id: uuid.UUID
    ) -> RoomResponse:
        room = await self._room(workspace_id, room_id, lock=True)
        if room.operational_status == RoomOperationalStatus.OCCUPIED:
            raise StayConflictError("An occupied room cannot be reset")
        room.operational_status = RoomOperationalStatus.AVAILABLE
        await self.session.commit()
        return await self.get_room(workspace_id, room_id)

    async def list_rooms(
        self,
        workspace_id: uuid.UUID,
        *,
        property_id: uuid.UUID | None,
        room_type_id: uuid.UUID | None,
        operational_status: RoomOperationalStatus | None,
        readiness_status: RoomReadinessStatus | None,
        active: bool | None,
        page: int,
        page_size: int,
    ) -> RoomListResponse:
        active_assignment = (
            select(StayRoomAssignment.stay_id)
            .where(
                StayRoomAssignment.room_id == HotelRoom.id,
                StayRoomAssignment.released_at.is_(None),
            )
            .correlate(HotelRoom)
            .limit(1)
            .scalar_subquery()
        )
        query = (
            select(HotelRoom, Property.name, RoomType.name, active_assignment)
            .join(
                Property,
                (Property.id == HotelRoom.property_id)
                & (Property.workspace_id == HotelRoom.workspace_id),
            )
            .join(
                RoomType,
                (RoomType.id == HotelRoom.room_type_id)
                & (RoomType.workspace_id == HotelRoom.workspace_id),
            )
            .where(HotelRoom.workspace_id == workspace_id)
        )
        if property_id is not None:
            query = query.where(HotelRoom.property_id == property_id)
        if room_type_id is not None:
            query = query.where(HotelRoom.room_type_id == room_type_id)
        if operational_status is not None:
            query = query.where(HotelRoom.operational_status == operational_status)
        if readiness_status is not None:
            query = query.where(HotelRoom.readiness_status == readiness_status)
        if active is not None:
            query = query.where(HotelRoom.active.is_(active))
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                query.order_by(Property.name, HotelRoom.code, HotelRoom.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return RoomListResponse(
            items=[self._room_response(*row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    async def get_room(
        self, workspace_id: uuid.UUID, room_id: uuid.UUID
    ) -> RoomResponse:
        active_assignment = (
            select(StayRoomAssignment.stay_id)
            .where(
                StayRoomAssignment.room_id == HotelRoom.id,
                StayRoomAssignment.released_at.is_(None),
            )
            .correlate(HotelRoom)
            .limit(1)
            .scalar_subquery()
        )
        row = (
            await self.session.execute(
                select(HotelRoom, Property.name, RoomType.name, active_assignment)
                .join(
                    Property,
                    (Property.id == HotelRoom.property_id)
                    & (Property.workspace_id == HotelRoom.workspace_id),
                )
                .join(
                    RoomType,
                    (RoomType.id == HotelRoom.room_type_id)
                    & (RoomType.workspace_id == HotelRoom.workspace_id),
                )
                .where(HotelRoom.workspace_id == workspace_id, HotelRoom.id == room_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Hotel room not found")
        return self._room_response(*row)

    async def create_stay_from_booking(
        self,
        workspace_id: uuid.UUID,
        booking_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> StayResponse:
        booking = await self.session.scalar(
            select(Booking)
            .where(Booking.workspace_id == workspace_id, Booking.id == booking_id)
            .with_for_update()
        )
        if booking is None:
            raise NotFoundError("Booking not found")
        existing = await self.session.scalar(
            select(Stay).where(
                Stay.workspace_id == workspace_id, Stay.booking_id == booking_id
            )
        )
        if existing is not None:
            await self.session.commit()
            return await self.get_stay(workspace_id, existing.id)
        if booking.status != BookingStatus.CONFIRMED:
            raise StayTransitionError("Only a confirmed booking can create a stay")
        item = await self._booking_item(workspace_id, booking_id)
        stay = Stay(
            workspace_id=workspace_id,
            booking_id=booking.id,
            property_id=booking.property_id,
            customer_id=booking.customer_id,
            status=StayStatus.EXPECTED,
            planned_check_in_date=booking.check_in,
            planned_check_out_date=booking.check_out,
            required_room_count=item.quantity,
        )
        self.session.add(stay)
        await self.session.flush()
        self._event(stay, StayEventType.STAY_CREATED, actor_user_id)
        await self.session.commit()
        return await self.get_stay(workspace_id, stay.id)

    async def assign_rooms(
        self,
        workspace_id: uuid.UUID,
        stay_id: uuid.UUID,
        room_ids: list[uuid.UUID],
        actor_user_id: uuid.UUID,
    ) -> StayResponse:
        stay = await self._stay(workspace_id, stay_id, lock=True)
        if stay.status != StayStatus.EXPECTED:
            raise StayTransitionError("Rooms can only be assigned to an expected stay")
        try:
            await self._assign_rooms_locked(stay, room_ids, actor_user_id)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise StayConflictError("A room was assigned concurrently") from exc
        return await self.get_stay(workspace_id, stay_id)

    async def check_in(
        self,
        workspace_id: uuid.UUID,
        stay_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        room_ids: list[uuid.UUID] | None = None,
    ) -> StayResponse:
        stay = await self._stay(workspace_id, stay_id, lock=True)
        if stay.status == StayStatus.CHECKED_IN:
            await self.session.commit()
            return await self.get_stay(workspace_id, stay_id)
        if stay.status != StayStatus.EXPECTED:
            raise StayTransitionError("Only an expected stay can be checked in")
        booking = await self.session.scalar(
            select(Booking).where(
                Booking.workspace_id == workspace_id, Booking.id == stay.booking_id
            )
        )
        if booking is None or booking.status != BookingStatus.CONFIRMED:
            raise StayTransitionError("Booking is no longer confirmed")
        try:
            if room_ids is not None:
                await self._assign_rooms_locked(stay, room_ids, actor_user_id)
            assignments = await self._active_assignments(stay, lock=True)
            if len(assignments) != stay.required_room_count:
                raise StayValidationError("All required rooms must be assigned")
            rooms = await self._lock_rooms(
                workspace_id, [assignment.room_id for assignment in assignments]
            )
            if len(rooms) != stay.required_room_count:
                raise StayValidationError("Assigned room is unavailable")
            for room in rooms:
                if (
                    not room.active
                    or room.operational_status != RoomOperationalStatus.AVAILABLE
                    or room.readiness_status != RoomReadinessStatus.READY
                ):
                    raise StayConflictError(
                        "Assigned room is not operationally available"
                    )
                room.operational_status = RoomOperationalStatus.OCCUPIED
            now = datetime.now(UTC)
            stay.status = StayStatus.CHECKED_IN
            stay.actual_check_in_at = now
            self._event(stay, StayEventType.CHECKED_IN, actor_user_id)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise StayConflictError("A room was occupied concurrently") from exc
        return await self.get_stay(workspace_id, stay_id)

    async def check_out(
        self, workspace_id: uuid.UUID, stay_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> StayResponse:
        stay = await self._stay(workspace_id, stay_id, lock=True)
        if stay.status == StayStatus.CHECKED_OUT:
            await self.session.commit()
            return await self.get_stay(workspace_id, stay_id)
        if stay.status != StayStatus.CHECKED_IN:
            raise StayTransitionError("Only an in-house stay can be checked out")
        assignments = await self._active_assignments(stay, lock=True)
        rooms = await self._lock_rooms(
            workspace_id, [assignment.room_id for assignment in assignments]
        )
        if any(
            room.operational_status != RoomOperationalStatus.OCCUPIED for room in rooms
        ):
            raise StayConflictError("Room occupancy state is inconsistent")
        now = datetime.now(UTC)
        for room in rooms:
            room.operational_status = RoomOperationalStatus.AVAILABLE
            room.readiness_status = RoomReadinessStatus.DIRTY
            task = HousekeepingTask(
                id=uuid.uuid4(),
                workspace_id=stay.workspace_id,
                property_id=stay.property_id,
                room_id=room.id,
                stay_id=stay.id,
                status=HousekeepingTaskStatus.PENDING,
                priority=HousekeepingPriority.NORMAL,
                created_by_user_id=actor_user_id,
                source="CHECKOUT",
            )
            self.session.add(task)
            await self.session.flush()
            self.session.add_all(
                [
                    HousekeepingEvent(
                        workspace_id=stay.workspace_id,
                        property_id=stay.property_id,
                        task_id=task.id,
                        room_id=room.id,
                        event_type=HousekeepingEventType.ROOM_DIRTY,
                        actor_user_id=actor_user_id,
                        event_metadata={},
                    ),
                    HousekeepingEvent(
                        workspace_id=stay.workspace_id,
                        property_id=stay.property_id,
                        task_id=task.id,
                        room_id=room.id,
                        event_type=HousekeepingEventType.HOUSEKEEPING_TASK_CREATED,
                        actor_user_id=actor_user_id,
                        event_metadata={},
                    ),
                ]
            )
        for assignment in assignments:
            assignment.released_at = now
        stay.status = StayStatus.CHECKED_OUT
        stay.actual_check_out_at = now
        self._event(stay, StayEventType.CHECKED_OUT, actor_user_id)
        await self.session.commit()
        return await self.get_stay(workspace_id, stay_id)

    async def mark_no_show(
        self, workspace_id: uuid.UUID, stay_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> StayResponse:
        stay = await self._stay(workspace_id, stay_id, lock=True)
        if stay.status == StayStatus.NO_SHOW:
            await self.session.commit()
            return await self.get_stay(workspace_id, stay_id)
        if stay.status != StayStatus.EXPECTED:
            raise StayTransitionError("Only an expected stay can be marked no-show")
        assignments = await self._active_assignments(stay, lock=True)
        rooms = await self._lock_rooms(
            workspace_id, [assignment.room_id for assignment in assignments]
        )
        if any(
            room.operational_status == RoomOperationalStatus.OCCUPIED for room in rooms
        ):
            raise StayConflictError("An occupied stay cannot be marked no-show")
        now = datetime.now(UTC)
        for assignment in assignments:
            assignment.released_at = now
            self._event(
                stay,
                StayEventType.ROOM_UNASSIGNED,
                actor_user_id,
                room_id=assignment.room_id,
            )
        stay.status = StayStatus.NO_SHOW
        self._event(stay, StayEventType.NO_SHOW, actor_user_id)
        await self.session.commit()
        return await self.get_stay(workspace_id, stay_id)

    async def list_stays(
        self,
        workspace_id: uuid.UUID,
        *,
        status: StayStatus | None,
        property_id: uuid.UUID | None,
        arrival_date: date | None,
        departure_date: date | None,
        page: int,
        page_size: int,
    ) -> StayListResponse:
        query = (
            select(Stay, Booking, Property.name, BookingItem.room_type_id)
            .join(
                Booking,
                (Booking.id == Stay.booking_id)
                & (Booking.workspace_id == Stay.workspace_id),
            )
            .join(
                Property,
                (Property.id == Stay.property_id)
                & (Property.workspace_id == Stay.workspace_id),
            )
            .join(
                BookingItem,
                (BookingItem.booking_id == Stay.booking_id)
                & (BookingItem.workspace_id == Stay.workspace_id),
            )
            .where(Stay.workspace_id == workspace_id)
        )
        if status is not None:
            query = query.where(Stay.status == status)
        if property_id is not None:
            query = query.where(Stay.property_id == property_id)
        if arrival_date is not None:
            query = query.where(Stay.planned_check_in_date == arrival_date)
        if departure_date is not None:
            query = query.where(Stay.planned_check_out_date == departure_date)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                query.order_by(Stay.planned_check_in_date, Stay.created_at, Stay.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        assignments = await self._assignment_summaries(
            workspace_id, [stay.id for stay, _, _, _ in rows]
        )
        return StayListResponse(
            items=[
                self._stay_response(
                    stay,
                    booking,
                    property_name,
                    room_type_id,
                    assignments.get(stay.id, []),
                    [],
                )
                for stay, booking, property_name, room_type_id in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    async def get_stay(
        self, workspace_id: uuid.UUID, stay_id: uuid.UUID
    ) -> StayResponse:
        row = (
            await self.session.execute(
                select(Stay, Booking, Property.name, BookingItem.room_type_id)
                .join(
                    Booking,
                    (Booking.id == Stay.booking_id)
                    & (Booking.workspace_id == Stay.workspace_id),
                )
                .join(
                    Property,
                    (Property.id == Stay.property_id)
                    & (Property.workspace_id == Stay.workspace_id),
                )
                .join(
                    BookingItem,
                    (BookingItem.booking_id == Stay.booking_id)
                    & (BookingItem.workspace_id == Stay.workspace_id),
                )
                .where(Stay.workspace_id == workspace_id, Stay.id == stay_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Stay not found")
        stay, booking, property_name, room_type_id = row
        assignments = await self._assignment_summaries(workspace_id, [stay.id])
        events = list(
            (
                await self.session.scalars(
                    select(StayEvent)
                    .where(
                        StayEvent.workspace_id == workspace_id,
                        StayEvent.stay_id == stay_id,
                    )
                    .order_by(StayEvent.sequence)
                    .limit(500)
                )
            ).all()
        )
        return self._stay_response(
            stay,
            booking,
            property_name,
            room_type_id,
            assignments.get(stay.id, []),
            [StayEventResponse.model_validate(event) for event in events],
        )

    async def _assign_rooms_locked(
        self,
        stay: Stay,
        room_ids: list[uuid.UUID],
        actor_user_id: uuid.UUID,
    ) -> None:
        if len(room_ids) != stay.required_room_count:
            raise StayValidationError(
                f"Exactly {stay.required_room_count} room(s) must be assigned"
            )
        if len(set(room_ids)) != len(room_ids):
            raise StayValidationError("Room assignments must be unique")
        item = await self._booking_item(stay.workspace_id, stay.booking_id)
        current = await self._active_assignments(stay, lock=True)
        current_by_room = {assignment.room_id: assignment for assignment in current}
        all_room_ids = sorted(set(room_ids) | set(current_by_room), key=str)
        rooms = await self._lock_rooms(stay.workspace_id, all_room_ids)
        rooms_by_id = {room.id: room for room in rooms}
        requested = [rooms_by_id.get(room_id) for room_id in room_ids]
        if any(room is None for room in requested):
            raise NotFoundError("Hotel room not found")
        for room in requested:
            if (
                room.property_id != stay.property_id
                or room.room_type_id != item.room_type_id
            ):
                raise StayValidationError("Room does not match booking property/type")
            if not room.active:
                raise StayConflictError("Inactive room cannot be assigned")
            if room.operational_status == RoomOperationalStatus.OUT_OF_SERVICE:
                raise StayConflictError("Out-of-service room cannot be assigned")
            if room.operational_status == RoomOperationalStatus.OCCUPIED:
                raise StayConflictError("Occupied room cannot be assigned")
            if room.readiness_status != RoomReadinessStatus.READY:
                raise StayConflictError("Room is not ready for guest assignment")
        conflicts = list(
            (
                await self.session.scalars(
                    select(StayRoomAssignment).where(
                        StayRoomAssignment.room_id.in_(room_ids),
                        StayRoomAssignment.released_at.is_(None),
                        StayRoomAssignment.stay_id != stay.id,
                    )
                )
            ).all()
        )
        if conflicts:
            raise StayConflictError("Room already has an active assignment")
        now = datetime.now(UTC)
        for room_id, assignment in current_by_room.items():
            if room_id not in room_ids:
                assignment.released_at = now
                self._event(
                    stay,
                    StayEventType.ROOM_UNASSIGNED,
                    actor_user_id,
                    room_id=room_id,
                )
        for room_id in room_ids:
            if room_id not in current_by_room:
                self.session.add(
                    StayRoomAssignment(
                        workspace_id=stay.workspace_id,
                        property_id=stay.property_id,
                        stay_id=stay.id,
                        room_id=room_id,
                        assigned_by_user_id=actor_user_id,
                    )
                )
                self._event(
                    stay,
                    StayEventType.ROOM_ASSIGNED,
                    actor_user_id,
                    room_id=room_id,
                )
        await self.session.flush()

    async def _catalog_room_type(self, workspace_id, property_id, room_type_id):
        prop = await self.session.scalar(
            select(Property).where(
                Property.workspace_id == workspace_id, Property.id == property_id
            )
        )
        room_type = await self.session.scalar(
            select(RoomType).where(
                RoomType.workspace_id == workspace_id,
                RoomType.property_id == property_id,
                RoomType.id == room_type_id,
            )
        )
        if prop is None or room_type is None:
            raise NotFoundError("Hotel catalog resource not found")
        return prop, room_type

    async def _room(self, workspace_id, room_id, *, lock=False):
        query = select(HotelRoom).where(
            HotelRoom.workspace_id == workspace_id, HotelRoom.id == room_id
        )
        if lock:
            query = query.with_for_update()
        room = await self.session.scalar(query)
        if room is None:
            raise NotFoundError("Hotel room not found")
        return room

    async def _stay(self, workspace_id, stay_id, *, lock=False):
        query = select(Stay).where(
            Stay.workspace_id == workspace_id, Stay.id == stay_id
        )
        if lock:
            query = query.with_for_update()
        stay = await self.session.scalar(query)
        if stay is None:
            raise NotFoundError("Stay not found")
        return stay

    async def _booking_item(self, workspace_id, booking_id):
        item = await self.session.scalar(
            select(BookingItem).where(
                BookingItem.workspace_id == workspace_id,
                BookingItem.booking_id == booking_id,
            )
        )
        if item is None:
            raise NotFoundError("Booking item not found")
        return item

    async def _active_assignments(self, stay: Stay, *, lock=False):
        query = select(StayRoomAssignment).where(
            StayRoomAssignment.workspace_id == stay.workspace_id,
            StayRoomAssignment.stay_id == stay.id,
            StayRoomAssignment.released_at.is_(None),
        )
        if lock:
            query = query.with_for_update()
        return list((await self.session.scalars(query)).all())

    async def _lock_rooms(self, workspace_id, room_ids):
        if not room_ids:
            return []
        return list(
            (
                await self.session.scalars(
                    select(HotelRoom)
                    .where(
                        HotelRoom.workspace_id == workspace_id,
                        HotelRoom.id.in_(room_ids),
                    )
                    .order_by(HotelRoom.id)
                    .with_for_update()
                )
            ).all()
        )

    async def _ensure_room_unassigned(self, room: HotelRoom) -> None:
        assigned = await self.session.scalar(
            select(StayRoomAssignment.id).where(
                StayRoomAssignment.room_id == room.id,
                StayRoomAssignment.released_at.is_(None),
            )
        )
        if assigned is not None:
            raise StayConflictError(
                "Assigned room cannot change operational availability"
            )

    async def _assignment_summaries(self, workspace_id, stay_ids):
        result: dict[uuid.UUID, list[StayRoomSummary]] = {
            stay_id: [] for stay_id in stay_ids
        }
        if not stay_ids:
            return result
        rows = (
            await self.session.execute(
                select(StayRoomAssignment, HotelRoom)
                .join(
                    HotelRoom,
                    (HotelRoom.id == StayRoomAssignment.room_id)
                    & (HotelRoom.workspace_id == StayRoomAssignment.workspace_id),
                )
                .where(
                    StayRoomAssignment.workspace_id == workspace_id,
                    StayRoomAssignment.stay_id.in_(stay_ids),
                )
                .order_by(StayRoomAssignment.assigned_at, HotelRoom.code)
                .limit(2000)
            )
        ).all()
        for assignment, room in rows:
            result[assignment.stay_id].append(
                StayRoomSummary(
                    assignment_id=assignment.id,
                    room_id=room.id,
                    code=room.code,
                    room_type_id=room.room_type_id,
                    operational_status=room.operational_status,
                    readiness_status=room.readiness_status,
                    assigned_at=assignment.assigned_at,
                    released_at=assignment.released_at,
                )
            )
        return result

    @staticmethod
    def _room_response(room, property_name, room_type_name, current_stay_id):
        return RoomResponse(
            id=room.id,
            workspace_id=room.workspace_id,
            property_id=room.property_id,
            property_name=property_name,
            room_type_id=room.room_type_id,
            room_type_name=room_type_name,
            code=room.code,
            floor=room.floor,
            active=room.active,
            operational_status=room.operational_status,
            readiness_status=room.readiness_status,
            current_stay_id=current_stay_id,
            created_at=room.created_at,
            updated_at=room.updated_at,
        )

    @staticmethod
    def _stay_response(stay, booking, property_name, room_type_id, rooms, events):
        return StayResponse(
            id=stay.id,
            workspace_id=stay.workspace_id,
            booking_id=stay.booking_id,
            property_id=stay.property_id,
            property_name=property_name,
            room_type_id=room_type_id,
            customer_id=stay.customer_id,
            guest_name=booking.guest_name,
            status=stay.status,
            planned_check_in_date=stay.planned_check_in_date,
            planned_check_out_date=stay.planned_check_out_date,
            required_room_count=stay.required_room_count,
            actual_check_in_at=stay.actual_check_in_at,
            actual_check_out_at=stay.actual_check_out_at,
            rooms=rooms,
            events=events,
            created_at=stay.created_at,
            updated_at=stay.updated_at,
        )

    def _event(
        self,
        stay: Stay,
        event_type: StayEventType,
        actor_user_id: uuid.UUID,
        *,
        room_id: uuid.UUID | None = None,
    ) -> None:
        self.session.add(
            StayEvent(
                workspace_id=stay.workspace_id,
                stay_id=stay.id,
                booking_id=stay.booking_id,
                property_id=stay.property_id,
                room_id=room_id,
                event_type=event_type,
                actor_user_id=actor_user_id,
                event_metadata={},
            )
        )
