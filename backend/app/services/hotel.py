"""Authoritative Hotel catalog, inventory, availability, and quote services."""

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError, WorkspaceAccessDeniedError
from app.models.booking import Booking, BookingItem, BookingStatus
from app.models.hotel import InventoryDate, Property, RatePlan, RoomType
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.repositories.hotel import (
    InventoryRepository,
    PropertyRepository,
    RatePlanRepository,
    RoomTypeRepository,
)
from app.schemas.hotel import (
    AvailabilitySearchRequest,
    AvailabilitySearchResponse,
    InventoryUpsert,
    NightlyRate,
    PropertyCreate,
    PropertyUpdate,
    RatePlanCreate,
    RatePlanUpdate,
    RoomAvailabilityResult,
    RoomTypeCreate,
    RoomTypeUpdate,
)


class HotelConflictError(AppError):
    status_code = 409
    code = "HOTEL_RESOURCE_CONFLICT"
    message = "Hotel resource conflicts with existing data"


class HotelValidationError(AppError):
    status_code = 422
    code = "HOTEL_VALIDATION_ERROR"
    message = "Hotel data is invalid"


class HotelCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.properties = PropertyRepository(session)
        self.room_types = RoomTypeRepository(session)
        self.rate_plans = RatePlanRepository(session)
        self.inventory = InventoryRepository(session)

    async def require_admin(self, workspace_id, user_id) -> None:
        role = await self.session.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if role not in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
            raise WorkspaceAccessDeniedError(
                "Only workspace owners and admins can manage Hotel data"
            )

    async def create_property(self, workspace_id, data: PropertyCreate):
        value = Property(workspace_id=workspace_id, **data.model_dump())
        self.session.add(value)
        await self.session.commit()
        await self.session.refresh(value)
        return value

    async def list_properties(self, workspace_id):
        return await self.properties.list(workspace_id)

    async def get_property(self, workspace_id, property_id):
        value = await self.properties.get(workspace_id, property_id)
        if value is None:
            raise NotFoundError("Hotel property not found")
        return value

    async def update_property(self, workspace_id, property_id, data: PropertyUpdate):
        value = await self.get_property(workspace_id, property_id)
        for key, item in data.model_dump(exclude_unset=True).items():
            setattr(value, key, item)
        await self.session.commit()
        await self.session.refresh(value)
        return value

    async def create_room_type(self, workspace_id, data: RoomTypeCreate):
        await self.get_property(workspace_id, data.property_id)
        duplicate = await self.session.scalar(
            select(RoomType.id).where(
                RoomType.property_id == data.property_id, RoomType.code == data.code
            )
        )
        if duplicate:
            raise HotelConflictError("Room type code already exists for this property")
        value = RoomType(workspace_id=workspace_id, **data.model_dump())
        self.session.add(value)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HotelConflictError(
                "Room type code already exists for this property"
            ) from exc
        await self.session.refresh(value)
        return value

    async def list_room_types(self, workspace_id, property_id=None):
        if property_id:
            await self.get_property(workspace_id, property_id)
        return await self.room_types.list(workspace_id, property_id)

    async def get_room_type(self, workspace_id, room_type_id):
        value = await self.room_types.get(workspace_id, room_type_id)
        if value is None:
            raise NotFoundError("Hotel room type not found")
        return value

    async def update_room_type(self, workspace_id, room_type_id, data: RoomTypeUpdate):
        value = await self.get_room_type(workspace_id, room_type_id)
        changes = data.model_dump(exclude_unset=True)
        state = {
            "max_adults": changes.get("max_adults", value.max_adults),
            "max_children": changes.get("max_children", value.max_children),
            "max_occupancy": changes.get("max_occupancy", value.max_occupancy),
            "base_capacity": changes.get("base_capacity", value.base_capacity),
        }
        if state["max_occupancy"] < state["max_adults"]:
            raise HotelValidationError("max_occupancy must be at least max_adults")
        if state["base_capacity"] > state["max_occupancy"]:
            raise HotelValidationError("base_capacity cannot exceed max_occupancy")
        for key, item in changes.items():
            setattr(value, key, item)
        await self.session.commit()
        await self.session.refresh(value)
        return value

    async def create_rate_plan(self, workspace_id, data: RatePlanCreate):
        property_value = await self.get_property(workspace_id, data.property_id)
        room_type = await self.get_room_type(workspace_id, data.room_type_id)
        if room_type.property_id != property_value.id:
            raise HotelValidationError("Room type does not belong to property")
        if data.currency != property_value.currency:
            raise HotelValidationError(
                "Rate plan currency must match property currency"
            )
        duplicate = await self.session.scalar(
            select(RatePlan.id).where(
                RatePlan.room_type_id == data.room_type_id, RatePlan.code == data.code
            )
        )
        if duplicate:
            raise HotelConflictError("Rate plan code already exists for this room type")
        value = RatePlan(workspace_id=workspace_id, **data.model_dump())
        self.session.add(value)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HotelConflictError(
                "Rate plan code already exists for this room type"
            ) from exc
        await self.session.refresh(value)
        return value

    async def list_rate_plans(self, workspace_id, property_id=None, room_type_id=None):
        if property_id:
            await self.get_property(workspace_id, property_id)
        if room_type_id:
            await self.get_room_type(workspace_id, room_type_id)
        return await self.rate_plans.list(workspace_id, property_id, room_type_id)

    async def get_rate_plan(self, workspace_id, rate_plan_id):
        value = await self.rate_plans.get(workspace_id, rate_plan_id)
        if value is None:
            raise NotFoundError("Hotel rate plan not found")
        return value

    async def update_rate_plan(self, workspace_id, rate_plan_id, data: RatePlanUpdate):
        value = await self.get_rate_plan(workspace_id, rate_plan_id)
        if data.currency is not None:
            property_value = await self.get_property(workspace_id, value.property_id)
            if data.currency != property_value.currency:
                raise HotelValidationError(
                    "Rate plan currency must match property currency"
                )
        for key, item in data.model_dump(exclude_unset=True).items():
            setattr(value, key, item)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HotelConflictError("Rate plan update conflicted") from exc
        await self.session.refresh(value)
        return value

    async def upsert_inventory(self, workspace_id, data: InventoryUpsert):
        await self.get_property(workspace_id, data.property_id)
        room_type = await self.get_room_type(workspace_id, data.room_type_id)
        if room_type.property_id != data.property_id:
            raise HotelValidationError("Room type does not belong to property")
        values = []
        day = data.start_date
        while day <= data.end_date:
            value = await self.inventory.get_day(
                workspace_id, room_type.id, day, for_update=True
            )
            if value is None:
                value = InventoryDate(
                    workspace_id=workspace_id,
                    property_id=data.property_id,
                    room_type_id=room_type.id,
                    inventory_date=day,
                )
                self.session.add(value)
            elif data.reserved_units != value.reserved_units:
                active_hold = await self.session.scalar(
                    select(Booking.id)
                    .join(BookingItem, BookingItem.booking_id == Booking.id)
                    .where(
                        Booking.workspace_id == workspace_id,
                        BookingItem.room_type_id == room_type.id,
                        Booking.status.in_(
                            (BookingStatus.HELD, BookingStatus.PENDING_PAYMENT)
                        ),
                        Booking.check_in <= day,
                        Booking.check_out > day,
                    )
                    .limit(1)
                )
                if active_hold is not None:
                    raise HotelConflictError(
                        "Reserved units cannot be edited while booking holds are active"
                    )
            value.total_units = data.total_units
            value.reserved_units = data.reserved_units
            value.blocked_units = data.blocked_units
            values.append(value)
            day += timedelta(days=1)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HotelConflictError("Inventory update conflicted") from exc
        for value in values:
            await self.session.refresh(value)
        return values


class HotelAvailabilityService:
    """Purely deterministic read-only availability and quote calculation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.catalog = HotelCatalogService(session)

    async def search(
        self, workspace_id: uuid.UUID, request: AvailabilitySearchRequest
    ) -> AvailabilitySearchResponse:
        property_value = await self.catalog.get_property(
            workspace_id, request.property_id
        )
        nights = (request.check_out - request.check_in).days
        if not property_value.active:
            return self._response(request, nights, [])

        room_types = await self.catalog.room_types.list(workspace_id, property_value.id)
        room_types = [
            room
            for room in room_types
            if room.active
            and (request.room_type_id is None or room.id == request.room_type_id)
            and request.adults <= room.max_adults
            and request.children <= room.max_children
            and request.adults + request.children <= room.max_occupancy
        ]
        inventory = await self.catalog.inventory.list_range(
            workspace_id, property_value.id, request.check_in, request.check_out
        )
        by_room = {}
        for row in inventory:
            by_room.setdefault(row.room_type_id, {})[row.inventory_date] = row

        results: list[RoomAvailabilityResult] = []
        for room in room_types:
            daily = by_room.get(room.id, {})
            expected_days = [
                request.check_in + timedelta(days=index) for index in range(nights)
            ]
            if any(day not in daily for day in expected_days):
                continue
            available = min(daily[day].available_units for day in expected_days)
            if available <= 0:
                continue
            plans = await self.catalog.rate_plans.list(
                workspace_id, property_value.id, room.id
            )
            for plan in plans:
                if not plan.active or (
                    request.rate_plan_id is not None and plan.id != request.rate_plan_id
                ):
                    continue
                nightly = [
                    NightlyRate(date=day, amount=plan.base_price)
                    for day in expected_days
                ]
                subtotal = sum((rate.amount for rate in nightly), Decimal("0.00"))
                results.append(
                    RoomAvailabilityResult(
                        property_id=property_value.id,
                        room_type_id=room.id,
                        room_type_name=room.name,
                        rate_plan_id=plan.id,
                        rate_plan_name=plan.name,
                        currency=plan.currency,
                        nightly_rates=nightly,
                        subtotal=subtotal,
                        available_units=available,
                        max_adults=room.max_adults,
                        max_children=room.max_children,
                        max_occupancy=room.max_occupancy,
                        refundable=plan.refundable,
                        cancellation_policy_summary=plan.cancellation_policy_summary,
                    )
                )
        results.sort(
            key=lambda item: (
                item.subtotal,
                str(item.room_type_id),
                str(item.rate_plan_id),
            )
        )
        return self._response(request, nights, results)

    async def quote(self, workspace_id, request):
        result = await self.search(workspace_id, request)
        if request.rate_plan_id is None:
            raise HotelValidationError("rate_plan_id is required for a quote")
        return result

    @staticmethod
    def _response(request, nights, results):
        return AvailabilitySearchResponse(
            check_in=request.check_in,
            check_out=request.check_out,
            nights=nights,
            results=results,
        )
