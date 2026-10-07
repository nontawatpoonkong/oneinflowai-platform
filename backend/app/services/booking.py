"""Transactional booking holds against authoritative Hotel inventory."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.booking import (
    Booking,
    BookingEvent,
    BookingEventType,
    BookingItem,
    BookingStatus,
)
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.hotel import InventoryDate, Property, RatePlan, RoomType
from app.schemas.booking import BookingHoldCreate
from app.services.hotel import HotelCatalogService

HOLD_DURATION = timedelta(minutes=15)
ACTIVE_STATES = (BookingStatus.HELD, BookingStatus.PENDING_PAYMENT)


class BookingUnavailableError(AppError):
    status_code = 409
    code = "BOOKING_UNAVAILABLE"
    message = "Requested inventory is unavailable"


class BookingConflictError(AppError):
    status_code = 409
    code = "BOOKING_CONFLICT"
    message = "Booking request conflicts with an existing hold"


class BookingTransitionError(AppError):
    status_code = 409
    code = "BOOKING_TRANSITION_INVALID"
    message = "Booking transition is not allowed"


class BookingValidationError(AppError):
    status_code = 422
    code = "BOOKING_VALIDATION_ERROR"
    message = "Booking request is invalid"


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.catalog = HotelCatalogService(session)

    async def require_admin(self, workspace_id, user_id) -> None:
        await self.catalog.require_admin(workspace_id, user_id)

    async def create_hold(
        self,
        workspace_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request: BookingHoldCreate,
        *,
        draft: bool = False,
    ) -> Booking:
        """Lock the idempotency key and all stay nights, then commit as one unit."""
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    **request.model_dump(mode="json"),
                    "_operation": "DRAFT" if draft else "HOLD",
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        try:
            # A transaction-scoped advisory lock serializes identical keys before
            # SELECT; the unique constraint remains the final database guard.
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
                {"value": f"hotel-booking:{workspace_id}:{request.idempotency_key}"},
            )
            existing = await self.session.scalar(
                select(Booking).where(
                    Booking.workspace_id == workspace_id,
                    Booking.idempotency_key == request.idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise BookingConflictError(
                        "Idempotency key was used for a different request"
                    )
                await self.session.commit()
                return existing

            # Lock catalog rows as well so a concurrent rate change cannot split
            # the immutable snapshot from its price/policy validation.
            prop = await self.session.scalar(
                select(Property)
                .where(
                    Property.workspace_id == workspace_id,
                    Property.id == request.property_id,
                )
                .with_for_update()
            )
            room = await self.session.scalar(
                select(RoomType)
                .where(
                    RoomType.workspace_id == workspace_id,
                    RoomType.property_id == request.property_id,
                    RoomType.id == request.room_type_id,
                )
                .with_for_update()
            )
            plan = await self.session.scalar(
                select(RatePlan)
                .where(
                    RatePlan.workspace_id == workspace_id,
                    RatePlan.property_id == request.property_id,
                    RatePlan.room_type_id == request.room_type_id,
                    RatePlan.id == request.rate_plan_id,
                )
                .with_for_update()
            )
            if not prop or not room or not plan:
                raise NotFoundError("Hotel booking catalog resource not found")
            if not prop.active or not room.active or not plan.active:
                raise BookingUnavailableError(
                    "Hotel booking catalog resource is inactive"
                )
            if plan.currency != prop.currency:
                raise BookingValidationError("Rate plan currency differs from property")
            if (
                request.adults > room.max_adults
                or request.children > room.max_children
                or request.adults + request.children > room.max_occupancy
            ):
                raise BookingValidationError("Occupancy exceeds room capacity")

            customer_id = request.customer_id
            if customer_id is not None:
                customer = await self.session.scalar(
                    select(Customer).where(
                        Customer.workspace_id == workspace_id,
                        Customer.id == customer_id,
                        Customer.deleted_at.is_(None),
                    )
                )
                if customer is None:
                    raise NotFoundError("Customer not found")
            if request.conversation_id is not None:
                conversation = await self.session.scalar(
                    select(Conversation).where(
                        Conversation.workspace_id == workspace_id,
                        Conversation.id == request.conversation_id,
                    )
                )
                if conversation is None:
                    raise NotFoundError("Conversation not found")
                if customer_id is not None and customer_id != conversation.customer_id:
                    raise BookingValidationError(
                        "Conversation belongs to a different customer"
                    )
                customer_id = conversation.customer_id

            days = [
                request.check_in + timedelta(days=i)
                for i in range((request.check_out - request.check_in).days)
            ]
            rows = []
            if not draft:
                rows = await self._lock_inventory(
                    workspace_id,
                    request.property_id,
                    request.room_type_id,
                    request.check_in,
                    request.check_out,
                    request.quantity,
                )

            nightly = [
                {"date": day.isoformat(), "amount": str(plan.base_price)}
                for day in days
            ]
            subtotal = plan.base_price * Decimal(len(days)) * request.quantity
            now = datetime.now(UTC)
            booking = Booking(
                workspace_id=workspace_id,
                property_id=prop.id,
                customer_id=customer_id,
                conversation_id=request.conversation_id,
                guest_name=request.guest_name,
                status=BookingStatus.DRAFT,
                check_in=request.check_in,
                check_out=request.check_out,
                adults=request.adults,
                children=request.children,
                currency=plan.currency,
                subtotal=subtotal,
                total_amount=subtotal,
                hold_expires_at=None if draft else now + HOLD_DURATION,
                idempotency_key=request.idempotency_key,
                request_fingerprint=fingerprint,
                source="STAFF",
                property_name_snapshot=prop.name,
            )
            self.session.add(booking)
            await self.session.flush()
            self.session.add(
                BookingItem(
                    workspace_id=workspace_id,
                    property_id=prop.id,
                    booking_id=booking.id,
                    room_type_id=room.id,
                    rate_plan_id=plan.id,
                    quantity=request.quantity,
                    nightly_rates=nightly,
                    subtotal=subtotal,
                    occupancy_snapshot={
                        "adults": request.adults,
                        "children": request.children,
                        "max_adults": room.max_adults,
                        "max_children": room.max_children,
                        "max_occupancy": room.max_occupancy,
                    },
                    rate_policy_snapshot={
                        "currency": plan.currency,
                        "base_price": str(plan.base_price),
                        "refundable": plan.refundable,
                        "cancellation_policy_summary": plan.cancellation_policy_summary,
                    },
                    room_type_name_snapshot=room.name,
                    rate_plan_name_snapshot=plan.name,
                )
            )
            self._event(
                booking, BookingEventType.BOOKING_CREATED, "HUMAN", actor_user_id
            )
            if not draft:
                for row in rows:
                    row.reserved_units += request.quantity
                booking.status = BookingStatus.HELD
                self._event(
                    booking,
                    BookingEventType.HOLD_CREATED,
                    "HUMAN",
                    actor_user_id,
                    {"quantity": request.quantity},
                )
            await self.session.commit()
            return booking
        except Exception:
            await self.session.rollback()
            raise

    async def create_draft(self, workspace_id, actor_user_id, request):
        return await self.create_hold(workspace_id, actor_user_id, request, draft=True)

    async def activate_draft(self, workspace_id, actor_user_id, booking_id):
        """Reprice from current catalog and reserve all nights when a draft is held."""
        try:
            booking = await self.session.scalar(
                select(Booking)
                .where(Booking.workspace_id == workspace_id, Booking.id == booking_id)
                .with_for_update()
            )
            if booking is None:
                raise NotFoundError("Booking not found")
            if booking.status != BookingStatus.DRAFT:
                raise BookingTransitionError()
            item = await self.session.scalar(
                select(BookingItem).where(
                    BookingItem.workspace_id == workspace_id,
                    BookingItem.booking_id == booking.id,
                )
            )
            prop = await self.session.scalar(
                select(Property)
                .where(
                    Property.workspace_id == workspace_id,
                    Property.id == booking.property_id,
                )
                .with_for_update()
            )
            room = await self.session.scalar(
                select(RoomType)
                .where(
                    RoomType.workspace_id == workspace_id,
                    RoomType.property_id == booking.property_id,
                    RoomType.id == item.room_type_id,
                )
                .with_for_update()
            )
            plan = await self.session.scalar(
                select(RatePlan)
                .where(
                    RatePlan.workspace_id == workspace_id,
                    RatePlan.property_id == booking.property_id,
                    RatePlan.room_type_id == item.room_type_id,
                    RatePlan.id == item.rate_plan_id,
                )
                .with_for_update()
            )
            if (
                not prop
                or not room
                or not plan
                or not (prop.active and room.active and plan.active)
            ):
                raise BookingUnavailableError(
                    "Hotel booking catalog resource is inactive"
                )
            if (
                booking.adults > room.max_adults
                or booking.children > room.max_children
                or booking.adults + booking.children > room.max_occupancy
            ):
                raise BookingValidationError("Occupancy exceeds room capacity")
            if plan.currency != prop.currency:
                raise BookingValidationError("Rate plan currency differs from property")
            rows = await self._lock_inventory(
                workspace_id,
                booking.property_id,
                item.room_type_id,
                booking.check_in,
                booking.check_out,
                item.quantity,
            )
            days = [
                booking.check_in + timedelta(days=i)
                for i in range((booking.check_out - booking.check_in).days)
            ]
            subtotal = plan.base_price * Decimal(len(days)) * item.quantity
            booking.property_name_snapshot = prop.name
            booking.currency = plan.currency
            booking.subtotal = subtotal
            booking.total_amount = subtotal
            booking.hold_expires_at = datetime.now(UTC) + HOLD_DURATION
            item.nightly_rates = [
                {"date": day.isoformat(), "amount": str(plan.base_price)}
                for day in days
            ]
            item.subtotal = subtotal
            item.room_type_name_snapshot = room.name
            item.rate_plan_name_snapshot = plan.name
            item.occupancy_snapshot = {
                "adults": booking.adults,
                "children": booking.children,
                "max_adults": room.max_adults,
                "max_children": room.max_children,
                "max_occupancy": room.max_occupancy,
            }
            item.rate_policy_snapshot = {
                "currency": plan.currency,
                "base_price": str(plan.base_price),
                "refundable": plan.refundable,
                "cancellation_policy_summary": plan.cancellation_policy_summary,
            }
            for row in rows:
                row.reserved_units += item.quantity
            booking.status = BookingStatus.HELD
            self._event(
                booking,
                BookingEventType.HOLD_CREATED,
                "HUMAN",
                actor_user_id,
                {"quantity": item.quantity},
            )
            await self.session.commit()
            return booking
        except Exception:
            await self.session.rollback()
            raise

    async def _lock_inventory(
        self, workspace_id, property_id, room_type_id, check_in, check_out, quantity
    ):
        days = [
            check_in + timedelta(days=i) for i in range((check_out - check_in).days)
        ]
        result = await self.session.execute(
            select(InventoryDate)
            .where(
                InventoryDate.workspace_id == workspace_id,
                InventoryDate.property_id == property_id,
                InventoryDate.room_type_id == room_type_id,
                InventoryDate.inventory_date >= check_in,
                InventoryDate.inventory_date < check_out,
            )
            .order_by(InventoryDate.inventory_date)
            .with_for_update()
        )
        rows = list(result.scalars())
        if [row.inventory_date for row in rows] != days or any(
            row.available_units < quantity for row in rows
        ):
            raise BookingUnavailableError()
        return rows

    async def list(self, workspace_id):
        result = await self.session.execute(
            select(Booking)
            .where(Booking.workspace_id == workspace_id)
            .order_by(Booking.created_at.desc(), Booking.id)
        )
        return list(result.scalars())

    async def get(self, workspace_id, booking_id):
        booking = await self.session.scalar(
            select(Booking).where(
                Booking.workspace_id == workspace_id, Booking.id == booking_id
            )
        )
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    async def detail(self, workspace_id, booking_id):
        booking = await self.get(workspace_id, booking_id)
        item = await self.session.scalar(
            select(BookingItem).where(
                BookingItem.workspace_id == workspace_id,
                BookingItem.booking_id == booking.id,
            )
        )
        events = list(
            (
                await self.session.execute(
                    select(BookingEvent)
                    .where(
                        BookingEvent.workspace_id == workspace_id,
                        BookingEvent.booking_id == booking.id,
                    )
                    .order_by(
                        BookingEvent.created_at,
                        case(
                            (
                                BookingEvent.event_type
                                == BookingEventType.BOOKING_CREATED,
                                0,
                            ),
                            else_=1,
                        ),
                        BookingEvent.id,
                    )
                )
            ).scalars()
        )
        return {
            **{
                column.name: getattr(booking, column.name)
                for column in Booking.__table__.columns
            },
            "item": item,
            "events": events,
        }

    async def cancel(self, workspace_id, actor_user_id, booking_id):
        return await self._transition(workspace_id, actor_user_id, booking_id, "cancel")

    async def advance_to_payment(self, workspace_id, actor_user_id, booking_id):
        return await self._transition(
            workspace_id, actor_user_id, booking_id, "payment"
        )

    async def expire(self, workspace_id, booking_id, *, now=None):
        return await self._transition(workspace_id, None, booking_id, "expire", now=now)

    async def expire_due_holds(self, workspace_id, *, now=None, limit=100):
        now = now or datetime.now(UTC)
        result = await self.session.execute(
            select(Booking.id)
            .where(
                Booking.workspace_id == workspace_id,
                Booking.status.in_(ACTIVE_STATES),
                Booking.hold_expires_at <= now,
            )
            .order_by(Booking.hold_expires_at, Booking.id)
            .limit(limit)
        )
        count = 0
        for booking_id in result.scalars():
            try:
                booking = await self.expire(workspace_id, booking_id, now=now)
            except BookingTransitionError:
                # The candidate may have been confirmed/cancelled after the
                # batch SELECT but before its row lock was acquired.
                continue
            if booking.status == BookingStatus.EXPIRED:
                count += 1
        return count

    async def _transition(
        self, workspace_id, actor_user_id, booking_id, operation, *, now=None
    ):
        now = now or datetime.now(UTC)
        try:
            booking = await self.session.scalar(
                select(Booking)
                .where(Booking.workspace_id == workspace_id, Booking.id == booking_id)
                .with_for_update()
            )
            if booking is None:
                raise NotFoundError("Booking not found")
            if operation == "payment":
                if (
                    booking.status != BookingStatus.HELD
                    or booking.hold_expires_at <= now
                ):
                    raise BookingTransitionError()
                booking.status = BookingStatus.PENDING_PAYMENT
                self._event(
                    booking,
                    BookingEventType.PENDING_PAYMENT_STARTED,
                    "HUMAN",
                    actor_user_id,
                )
            elif operation in {"cancel", "expire"}:
                target = (
                    BookingStatus.CANCELLED
                    if operation == "cancel"
                    else BookingStatus.EXPIRED
                )
                if booking.status == target:
                    await self.session.commit()
                    return booking
                if operation == "cancel" and booking.status == BookingStatus.DRAFT:
                    booking.status = BookingStatus.CANCELLED
                    self._event(
                        booking,
                        BookingEventType.BOOKING_CANCELLED,
                        "HUMAN",
                        actor_user_id,
                    )
                    await self.session.commit()
                    return booking
                if booking.status not in ACTIVE_STATES:
                    raise BookingTransitionError()
                if operation == "expire" and booking.hold_expires_at > now:
                    raise BookingTransitionError("Hold has not expired")
                if operation == "cancel" and booking.hold_expires_at <= now:
                    raise BookingTransitionError(
                        "Expired hold must be expired before cancellation"
                    )
                item = await self.session.scalar(
                    select(BookingItem).where(
                        BookingItem.workspace_id == workspace_id,
                        BookingItem.booking_id == booking.id,
                    )
                )
                rows = list(
                    (
                        await self.session.execute(
                            select(InventoryDate)
                            .where(
                                InventoryDate.workspace_id == workspace_id,
                                InventoryDate.room_type_id == item.room_type_id,
                                InventoryDate.inventory_date >= booking.check_in,
                                InventoryDate.inventory_date < booking.check_out,
                            )
                            .order_by(InventoryDate.inventory_date)
                            .with_for_update()
                        )
                    ).scalars()
                )
                if len(rows) != (booking.check_out - booking.check_in).days or any(
                    row.reserved_units < item.quantity for row in rows
                ):
                    raise BookingConflictError("Reserved inventory is inconsistent")
                for row in rows:
                    row.reserved_units -= item.quantity
                booking.status = target
                self._event(
                    booking,
                    BookingEventType.BOOKING_CANCELLED
                    if operation == "cancel"
                    else BookingEventType.HOLD_EXPIRED,
                    "HUMAN" if operation == "cancel" else "SYSTEM",
                    actor_user_id,
                )
            await self.session.commit()
            return booking
        except Exception:
            await self.session.rollback()
            raise

    def _event(self, booking, event_type, actor_type, actor_user_id, metadata=None):
        self.session.add(
            BookingEvent(
                workspace_id=booking.workspace_id,
                booking_id=booking.id,
                event_type=event_type,
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                event_metadata=metadata or {},
            )
        )
