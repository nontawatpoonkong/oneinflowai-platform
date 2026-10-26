"""Workspace-scoped Hotel catalog, inventory, availability, and quote APIs."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.payment import PaymentApplicationReason, PaymentApplicationStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.booking import (
    BookingConfirmFromPayment,
    BookingHoldCreate,
    BookingPaymentCreate,
    BookingPaymentExceptionResponse,
    BookingPaymentReviewAcknowledge,
    BookingResponse,
    ManualBookingQuoteRequest,
)
from app.schemas.hotel import (
    AvailabilitySearchRequest,
    InventoryResponse,
    InventoryUpsert,
    PropertyCreate,
    PropertyResponse,
    PropertyUpdate,
    RatePlanCreate,
    RatePlanResponse,
    RatePlanUpdate,
    RoomTypeCreate,
    RoomTypeResponse,
    RoomTypeUpdate,
)
from app.schemas.payment import PaymentResponse
from app.schemas.response import success_response
from app.services.booking import BookingService
from app.services.booking_payment_confirmation import (
    BookingPaymentConfirmationService,
    BookingPaymentError,
)
from app.services.booking_payment_reconciliation import (
    BookingPaymentReconciliationService,
)
from app.services.hotel import HotelAvailabilityService, HotelCatalogService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


def _data(schema, value):
    return schema.model_validate(value).model_dump(mode="json")


def _payment_exception(payment, booking, reason):
    return BookingPaymentExceptionResponse(
        payment_id=payment.id,
        booking_id=booking.id,
        customer_id=payment.customer_id,
        payment_status=payment.status,
        application_status=payment.booking_application_status,
        reason=reason,
        booking_status=booking.status,
        payment_expected_amount=payment.expected_amount,
        payment_verified_amount=payment.verified_amount,
        payment_currency=payment.currency,
        booking_total_amount=booking.total_amount,
        booking_currency=booking.currency,
        payment_verified_at=payment.verified_at,
        booking_hold_expires_at=booking.hold_expires_at,
        review_note=payment.booking_review_note,
        reviewed_at=payment.booking_reviewed_at,
    ).model_dump(mode="json")


async def _admin(service, workspace, user):
    await service.require_admin(workspace.id, user.id)


async def _capability(session, workspace, user, capability):
    await WorkspaceCapabilityService(session).require(workspace.id, user.id, capability)


@router.get("/properties")
async def list_properties(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    values = await HotelCatalogService(session).list_properties(workspace.id)
    return success_response([_data(PropertyResponse, value) for value in values])


@router.post("/properties", status_code=status.HTTP_201_CREATED)
async def create_property(
    payload: PropertyCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = HotelCatalogService(session)
    await _admin(service, workspace, user)
    return success_response(
        _data(PropertyResponse, await service.create_property(workspace.id, payload)),
        "Property created",
    )


@router.get("/properties/{property_id}")
async def get_property(
    property_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    return success_response(
        _data(
            PropertyResponse,
            await HotelCatalogService(session).get_property(workspace.id, property_id),
        )
    )


@router.patch("/properties/{property_id}")
async def update_property(
    property_id: uuid.UUID,
    payload: PropertyUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = HotelCatalogService(session)
    await _admin(service, workspace, user)
    return success_response(
        _data(
            PropertyResponse,
            await service.update_property(workspace.id, property_id, payload),
        )
    )


@router.get("/room-types")
async def list_room_types(
    property_id: uuid.UUID | None = None,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    values = await HotelCatalogService(session).list_room_types(
        workspace.id, property_id
    )
    return success_response([_data(RoomTypeResponse, value) for value in values])


@router.post("/room-types", status_code=status.HTTP_201_CREATED)
async def create_room_type(
    payload: RoomTypeCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = HotelCatalogService(session)
    await _admin(service, workspace, user)
    return success_response(
        _data(RoomTypeResponse, await service.create_room_type(workspace.id, payload)),
        "Room type created",
    )


@router.get("/room-types/{room_type_id}")
async def get_room_type(
    room_type_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    return success_response(
        _data(
            RoomTypeResponse,
            await HotelCatalogService(session).get_room_type(
                workspace.id, room_type_id
            ),
        )
    )


@router.patch("/room-types/{room_type_id}")
async def update_room_type(
    room_type_id: uuid.UUID,
    payload: RoomTypeUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = HotelCatalogService(session)
    await _admin(service, workspace, user)
    return success_response(
        _data(
            RoomTypeResponse,
            await service.update_room_type(workspace.id, room_type_id, payload),
        )
    )


@router.get("/rate-plans")
async def list_rate_plans(
    property_id: uuid.UUID | None = None,
    room_type_id: uuid.UUID | None = None,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    values = await HotelCatalogService(session).list_rate_plans(
        workspace.id, property_id, room_type_id
    )
    return success_response([_data(RatePlanResponse, value) for value in values])


@router.post("/rate-plans", status_code=status.HTTP_201_CREATED)
async def create_rate_plan(
    payload: RatePlanCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = HotelCatalogService(session)
    await _admin(service, workspace, user)
    return success_response(
        _data(RatePlanResponse, await service.create_rate_plan(workspace.id, payload)),
        "Rate plan created",
    )


@router.get("/rate-plans/{rate_plan_id}")
async def get_rate_plan(
    rate_plan_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    return success_response(
        _data(
            RatePlanResponse,
            await HotelCatalogService(session).get_rate_plan(
                workspace.id, rate_plan_id
            ),
        )
    )


@router.patch("/rate-plans/{rate_plan_id}")
async def update_rate_plan(
    rate_plan_id: uuid.UUID,
    payload: RatePlanUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = HotelCatalogService(session)
    await _admin(service, workspace, user)
    return success_response(
        _data(
            RatePlanResponse,
            await service.update_rate_plan(workspace.id, rate_plan_id, payload),
        )
    )


@router.put("/inventory")
async def upsert_inventory(
    payload: InventoryUpsert,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = HotelCatalogService(session)
    await _admin(service, workspace, user)
    values = await service.upsert_inventory(workspace.id, payload)
    return success_response(
        [_data(InventoryResponse, value) for value in values], "Inventory updated"
    )


@router.get("/inventory")
async def list_inventory(
    property_id: uuid.UUID,
    start_date: str = Query(...),
    end_date: str = Query(...),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    request = AvailabilitySearchRequest(
        property_id=property_id, check_in=start_date, check_out=end_date, adults=1
    )
    service = HotelCatalogService(session)
    await service.get_property(workspace.id, property_id)
    values = await service.inventory.list_range(
        workspace.id, property_id, request.check_in, request.check_out
    )
    return success_response([_data(InventoryResponse, value) for value in values])


@router.post("/availability/search")
async def search_availability(
    payload: AvailabilitySearchRequest,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    # Read-only over the catalog, inventory and prices, like GET /inventory.
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    data = await HotelAvailabilityService(session).search(workspace.id, payload)
    return success_response(data.model_dump(mode="json"))


@router.post("/quotes")
async def quote(
    payload: AvailabilitySearchRequest,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    data = await HotelAvailabilityService(session).quote(workspace.id, payload)
    return success_response(data.model_dump(mode="json"))


@router.post("/bookings/hold", status_code=status.HTTP_201_CREATED)
async def create_booking_hold(
    payload: BookingHoldCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = BookingService(session)
    await _capability(session, workspace, user, WorkspaceCapability.BOOKING_CREATE)
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    booking = await service.create_hold(workspace.id, user.id, payload)
    return success_response(
        _data(BookingResponse, await service.detail(workspace.id, booking.id)),
        "Booking hold created",
    )


@router.post("/bookings/manual-quote")
async def manual_booking_quote(
    payload: ManualBookingQuoteRequest,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _capability(session, workspace, user, WorkspaceCapability.BOOKING_CREATE)
    await _capability(session, workspace, user, WorkspaceCapability.ROOM_READ)
    data = await BookingService(session).manual_quote(workspace.id, payload)
    return success_response(jsonable_encoder(data, custom_encoder={Decimal: str}))


@router.post("/bookings/draft", status_code=status.HTTP_201_CREATED)
async def create_booking_draft(
    payload: BookingHoldCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = BookingService(session)
    await _capability(session, workspace, user, WorkspaceCapability.BOOKING_CREATE)
    booking = await service.create_draft(workspace.id, user.id, payload)
    return success_response(
        _data(BookingResponse, await service.detail(workspace.id, booking.id)),
        "Booking draft created",
    )


@router.get("/bookings")
async def list_bookings(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = BookingService(session)
    await _capability(session, workspace, user, WorkspaceCapability.BOOKING_READ)
    bookings = await service.list(workspace.id)
    return success_response(
        [
            _data(BookingResponse, await service.detail(workspace.id, booking.id))
            for booking in bookings
        ]
    )


@router.get("/payment-exceptions")
async def list_booking_payment_exceptions(
    reason: PaymentApplicationReason | None = None,
    application_status: PaymentApplicationStatus | None = None,
    limit: int = Query(default=100, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    # Payment exception data (amounts, customer links, review notes) needs
    # payment.read; Workspace membership alone is not sufficient.
    await _capability(session, workspace, user, WorkspaceCapability.PAYMENT_READ)
    rows = await BookingPaymentReconciliationService(session).list_exceptions(
        workspace.id,
        reason=reason,
        application_status=application_status,
        limit=limit,
    )
    return success_response(
        [_payment_exception(payment, booking, code) for payment, booking, code in rows]
    )


@router.post("/payment-exceptions/{payment_id}/reconcile")
async def retry_booking_payment_reconciliation(
    payment_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await BookingService(session).require_admin(workspace.id, user.id)
    payment, booking = await BookingPaymentReconciliationService(
        session
    ).reconcile_payment(workspace.id, payment_id, actor_user_id=user.id)
    return success_response(
        _payment_exception(payment, booking, payment.booking_application_reason)
    )


@router.post("/payment-exceptions/{payment_id}/acknowledge")
async def acknowledge_booking_payment_exception(
    payment_id: uuid.UUID,
    payload: BookingPaymentReviewAcknowledge,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await BookingService(session).require_admin(workspace.id, user.id)
    payment, booking = await BookingPaymentReconciliationService(session).acknowledge(
        workspace.id, payment_id, user.id, payload.note
    )
    return success_response(
        _payment_exception(payment, booking, payment.booking_application_reason)
    )


@router.post("/bookings/expire-due")
async def expire_due_bookings(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = BookingService(session)
    await service.require_admin(workspace.id, user.id)
    count = await service.expire_due_holds(workspace.id)
    return success_response({"expired_count": count})


@router.get("/bookings/{booking_id}")
async def get_booking(
    booking_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = BookingService(session)
    await _capability(session, workspace, user, WorkspaceCapability.BOOKING_READ)
    return success_response(
        _data(BookingResponse, await service.detail(workspace.id, booking_id))
    )


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = BookingService(session)
    await _capability(session, workspace, user, WorkspaceCapability.BOOKING_CANCEL)
    await service.cancel(workspace.id, user.id, booking_id)
    return success_response(
        _data(BookingResponse, await service.detail(workspace.id, booking_id))
    )


@router.post("/bookings/{booking_id}/hold")
async def activate_booking_draft(
    booking_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = BookingService(session)
    await service.require_admin(workspace.id, user.id)
    await service.activate_draft(workspace.id, user.id, booking_id)
    return success_response(
        _data(BookingResponse, await service.detail(workspace.id, booking_id))
    )


@router.post("/bookings/{booking_id}/advance-to-payment")
async def advance_booking_to_payment(
    booking_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = BookingService(session)
    await service.require_admin(workspace.id, user.id)
    await service.advance_to_payment(workspace.id, user.id, booking_id)
    return success_response(
        _data(BookingResponse, await service.detail(workspace.id, booking_id))
    )


@router.post("/bookings/{booking_id}/payment", status_code=status.HTTP_201_CREATED)
async def initiate_booking_payment(
    booking_id: uuid.UUID,
    payload: BookingPaymentCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await BookingService(session).require_admin(workspace.id, user.id)
    payment = await BookingPaymentConfirmationService(session).initiate_payment(
        workspace.id, booking_id, payload.payment_destination_id, user.id
    )
    return success_response(_data(PaymentResponse, payment), "Booking payment linked")


@router.post("/bookings/{booking_id}/confirm-from-payment")
async def confirm_booking_from_payment(
    booking_id: uuid.UUID,
    payload: BookingConfirmFromPayment,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await BookingService(session).require_admin(workspace.id, user.id)
    payment, booking = await BookingPaymentReconciliationService(
        session
    ).reconcile_payment(
        workspace.id,
        payload.payment_id,
        actor_user_id=user.id,
        expected_booking_id=booking_id,
    )
    if payment.booking_applied_at is None:
        raise BookingPaymentError(
            payment.booking_application_reason
            or PaymentApplicationReason.PAYMENT_NOT_VERIFIED
        )
    return success_response(
        _data(
            BookingResponse,
            await BookingService(session).detail(workspace.id, booking_id),
        )
    )
