"""Trusted application boundary between customer payments and Hotel bookings."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.audit import AuditActorType, AuditArea
from app.models.booking import Booking, BookingEvent, BookingEventType, BookingStatus
from app.models.payment import (
    Payment,
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentDestination,
    PaymentStatus,
)
from app.services.audit import AuditService
from app.services.automation_events import emit_booking_event
from app.services.promotion import PromotionService


class BookingPaymentError(AppError):
    status_code = 409
    code = "BOOKING_PAYMENT_INVALID"
    message = "Booking payment cannot be applied"

    def __init__(self, reason: PaymentApplicationReason):
        self.reason = reason
        super().__init__(details={"reason": reason.value})


class BookingPaymentConfirmationService:
    """Booking owns the transition; Payment supplies verified facts only.

    Both operations lock the booking first. Confirmation then locks its payment,
    so expiry and concurrent confirmation cannot split the state transition.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def initiate_payment(
        self,
        workspace_id: uuid.UUID,
        booking_id: uuid.UUID,
        destination_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> Payment:
        try:
            booking = await self._lock_booking(workspace_id, booking_id)
            self._require_payable(booking)
            attempts = list(
                (
                    await self.session.execute(
                        select(Payment)
                        .where(
                            Payment.workspace_id == workspace_id,
                            Payment.booking_id == booking_id,
                        )
                        .order_by(Payment.created_at.desc(), Payment.id.desc())
                        .with_for_update()
                    )
                ).scalars()
            )
            latest = attempts[0] if attempts else None
            if latest and latest.status in {
                PaymentStatus.PENDING,
                PaymentStatus.VERIFYING,
            }:
                if latest.payment_destination_id != destination_id:
                    raise BookingPaymentError(
                        PaymentApplicationReason.BOOKING_LINK_CONFLICT
                    )
                await self.session.commit()
                return latest
            if any(
                attempt.status == PaymentStatus.VERIFIED
                or attempt.booking_applied_at is not None
                for attempt in attempts
            ):
                raise BookingPaymentError(
                    PaymentApplicationReason.BOOKING_ALREADY_CONFIRMED
                )
            if latest and latest.status not in {
                PaymentStatus.REJECTED,
                PaymentStatus.DUPLICATE,
                PaymentStatus.EXPIRED,
            }:
                raise BookingPaymentError(
                    PaymentApplicationReason.INVALID_BOOKING_STATE
                )
            destination = await self.session.scalar(
                select(PaymentDestination).where(
                    PaymentDestination.workspace_id == workspace_id,
                    PaymentDestination.id == destination_id,
                    PaymentDestination.is_active.is_(True),
                )
            )
            if not destination:
                raise NotFoundError("Payment destination not found")
            payment = Payment(
                workspace_id=workspace_id,
                booking_id=booking.id,
                payment_destination_id=destination.id,
                customer_id=booking.customer_id,
                conversation_id=booking.conversation_id,
                expected_amount=booking.total_amount,
                currency=booking.currency,
                expires_at=booking.hold_expires_at,
                status=PaymentStatus.PENDING,
                booking_application_status=PaymentApplicationStatus.UNAPPLIED,
            )
            self.session.add(payment)
            await self.session.flush()
            self.session.add(
                BookingEvent(
                    workspace_id=workspace_id,
                    booking_id=booking.id,
                    event_type=(
                        BookingEventType.REPLACEMENT_PAYMENT_LINKED
                        if latest
                        else BookingEventType.PAYMENT_LINKED
                    ),
                    actor_type="HUMAN" if actor_user_id else "SYSTEM",
                    actor_user_id=actor_user_id,
                    event_metadata={
                        "payment_id": str(payment.id),
                        **({"previous_payment_id": str(latest.id)} if latest else {}),
                    },
                )
            )
            AuditService(self.session).record(
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                actor_type=(
                    AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM
                ),
                action="PAYMENT_REPLACED" if latest else "PAYMENT_CREATED",
                area=AuditArea.PAYMENTS,
                resource_type="Payment",
                resource_id=payment.id,
                metadata={"booking_id": str(booking.id)},
            )
            await self.session.commit()
            return payment
        except Exception:
            await self.session.rollback()
            raise

    async def confirm(
        self,
        workspace_id: uuid.UUID,
        booking_id: uuid.UUID,
        payment_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> Booking:
        try:
            booking = await self._lock_booking(workspace_id, booking_id)
            payment = await self.session.scalar(
                select(Payment)
                .where(Payment.workspace_id == workspace_id, Payment.id == payment_id)
                .with_for_update()
            )
            if not payment or payment.booking_id != booking.id:
                raise BookingPaymentError(
                    PaymentApplicationReason.BOOKING_LINK_CONFLICT
                )
            if (
                booking.status == BookingStatus.CONFIRMED
                and payment.booking_applied_at is not None
            ):
                await self.session.commit()
                return booking
            reason = self.reason(booking, payment)
            if reason:
                raise BookingPaymentError(reason)
            await self.apply_locked(booking, payment, actor_user_id=actor_user_id)
            await self.session.commit()
            return booking
        except Exception:
            await self.session.rollback()
            raise

    async def _lock_booking(self, workspace_id, booking_id) -> Booking:
        booking = await self.session.scalar(
            select(Booking)
            .where(Booking.workspace_id == workspace_id, Booking.id == booking_id)
            .with_for_update()
        )
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    @staticmethod
    def _require_payable(booking: Booking) -> None:
        if booking.status != BookingStatus.PENDING_PAYMENT:
            raise BookingPaymentError(PaymentApplicationReason.INVALID_BOOKING_STATE)
        if booking.hold_expires_at is None or booking.hold_expires_at <= datetime.now(
            UTC
        ):
            raise BookingPaymentError(PaymentApplicationReason.BOOKING_EXPIRED)

    @staticmethod
    def reason(booking: Booking, payment: Payment) -> PaymentApplicationReason | None:
        if (
            payment.booking_id != booking.id
            or payment.workspace_id != booking.workspace_id
        ):
            return PaymentApplicationReason.BOOKING_LINK_CONFLICT
        if payment.booking_applied_at is not None:
            return PaymentApplicationReason.PAYMENT_ALREADY_APPLIED
        if payment.status != PaymentStatus.VERIFIED:
            return PaymentApplicationReason.PAYMENT_NOT_VERIFIED
        if booking.status == BookingStatus.EXPIRED or (
            booking.status == BookingStatus.PENDING_PAYMENT
            and (
                booking.hold_expires_at is None
                or booking.hold_expires_at <= datetime.now(UTC)
            )
        ):
            return PaymentApplicationReason.BOOKING_EXPIRED
        if booking.status == BookingStatus.CANCELLED:
            return PaymentApplicationReason.BOOKING_CANCELLED
        if booking.status == BookingStatus.CONFIRMED:
            return PaymentApplicationReason.BOOKING_ALREADY_CONFIRMED
        if booking.status != BookingStatus.PENDING_PAYMENT:
            return PaymentApplicationReason.INVALID_BOOKING_STATE
        if payment.currency != booking.currency:
            return PaymentApplicationReason.CURRENCY_MISMATCH
        if (
            payment.expected_amount != booking.total_amount
            or payment.verified_amount != booking.total_amount
        ):
            return PaymentApplicationReason.AMOUNT_MISMATCH
        return None

    async def apply_locked(
        self,
        booking: Booking,
        payment: Payment,
        *,
        actor_user_id: uuid.UUID | None,
    ) -> None:
        # Promotion quota is finalized under the same locked booking/payment
        # transaction. Repeated confirmation is idempotent by booking.
        await PromotionService(self.session).confirm_redemption(
            booking.workspace_id, booking.id
        )
        payment.booking_applied_at = datetime.now(UTC)
        payment.booking_application_status = PaymentApplicationStatus.APPLIED
        payment.booking_application_reason = None
        booking.status = BookingStatus.CONFIRMED
        booking.hold_expires_at = None
        self.session.add(
            BookingEvent(
                workspace_id=booking.workspace_id,
                booking_id=booking.id,
                event_type=BookingEventType.BOOKING_CONFIRMED,
                actor_type="HUMAN" if actor_user_id else "SYSTEM",
                actor_user_id=actor_user_id,
                event_metadata={"payment_id": str(payment.id)},
            )
        )
        AuditService(self.session).record(
            workspace_id=booking.workspace_id,
            actor_user_id=actor_user_id,
            actor_type=(
                AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM
            ),
            action="PAYMENT_APPLIED",
            area=AuditArea.PAYMENTS,
            resource_type="Payment",
            resource_id=payment.id,
            metadata={"booking_id": str(booking.id)},
        )
        AuditService(self.session).record(
            workspace_id=booking.workspace_id,
            actor_user_id=actor_user_id,
            actor_type=(
                AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM
            ),
            action="BOOKING_CONFIRMED",
            area=AuditArea.BOOKINGS,
            resource_type="Booking",
            resource_id=booking.id,
            metadata={"payment_id": str(payment.id)},
        )
        await emit_booking_event(self.session, booking, "hotel.booking.confirmed")
