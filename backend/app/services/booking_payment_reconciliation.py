"""Operational reconciliation of verified customer payments and Hotel bookings."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.booking import Booking, BookingEvent, BookingEventType, BookingStatus
from app.models.payment import (
    Payment,
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentStatus,
)
from app.services.booking_payment_confirmation import (
    BookingPaymentConfirmationService,
    BookingPaymentError,
)


class BookingPaymentReconciliationService:
    """Lock Booking first; delegate every successful application to its owner."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.confirmation = BookingPaymentConfirmationService(session)

    async def reconcile_payment(
        self,
        workspace_id: uuid.UUID,
        payment_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
        expected_booking_id: uuid.UUID | None = None,
    ) -> tuple[Payment, Booking]:
        try:
            # The booking link is immutable through public APIs. Read it first
            # solely to establish the common booking-then-payment lock order.
            payment_link = (
                await self.session.execute(
                    select(Payment.id, Payment.booking_id).where(
                        Payment.workspace_id == workspace_id,
                        Payment.id == payment_id,
                    )
                )
            ).one_or_none()
            if payment_link is None:
                raise NotFoundError("Booking payment not found")
            booking_id = payment_link.booking_id
            if booking_id is None:
                raise BookingPaymentError(
                    PaymentApplicationReason.BOOKING_LINK_CONFLICT
                )
            if expected_booking_id is not None and booking_id != expected_booking_id:
                raise BookingPaymentError(
                    PaymentApplicationReason.BOOKING_LINK_CONFLICT
                )
            booking = await self.confirmation._lock_booking(workspace_id, booking_id)
            payment = await self.session.scalar(
                select(Payment)
                .where(Payment.workspace_id == workspace_id, Payment.id == payment_id)
                .with_for_update()
            )
            if payment is None or payment.booking_id != booking.id:
                raise NotFoundError("Booking payment not found")
            if (
                payment.booking_applied_at is not None
                and booking.status == BookingStatus.CONFIRMED
            ):
                await self.session.commit()
                return payment, booking
            reason = self.confirmation.reason(booking, payment)
            if reason is None:
                self.confirmation.apply_locked(
                    booking, payment, actor_user_id=actor_user_id
                )
            elif payment.status == PaymentStatus.VERIFIED:
                changed = (
                    payment.booking_application_status
                    != PaymentApplicationStatus.REQUIRES_REVIEW
                    or payment.booking_application_reason != reason
                )
                payment.booking_application_status = (
                    PaymentApplicationStatus.REQUIRES_REVIEW
                )
                payment.booking_application_reason = reason
                if changed:
                    self._event(
                        booking,
                        payment,
                        BookingEventType.PAYMENT_REQUIRES_REVIEW,
                        actor_user_id,
                        {"reason": reason.value},
                    )
            else:
                payment.booking_application_status = PaymentApplicationStatus.UNAPPLIED
                payment.booking_application_reason = (
                    PaymentApplicationReason.PAYMENT_NOT_VERIFIED
                )
            await self.session.commit()
            return payment, booking
        except Exception:
            await self.session.rollback()
            raise

    async def list_exceptions(
        self,
        workspace_id: uuid.UUID,
        *,
        reason: PaymentApplicationReason | None = None,
        application_status: PaymentApplicationStatus | None = None,
        limit: int = 100,
    ) -> list[tuple[Payment, Booking, PaymentApplicationReason]]:
        # Include legacy/unclassified verified payments so a missed notification
        # cannot hide money. Never return payment evidence or provider payloads.
        query = (
            select(Payment, Booking)
            .join(
                Booking,
                (Payment.booking_id == Booking.id)
                & (Payment.workspace_id == Booking.workspace_id),
            )
            .where(
                Payment.workspace_id == workspace_id,
                Payment.status == PaymentStatus.VERIFIED,
                Payment.booking_applied_at.is_(None),
            )
        )
        if reason is not None:
            query = query.where(Payment.booking_application_reason == reason)
        if application_status is not None:
            query = query.where(
                Payment.booking_application_status == application_status
            )
        rows = (
            await self.session.execute(
                query.order_by(Payment.verified_at.desc(), Payment.id).limit(limit)
            )
        ).all()
        result = []
        for payment, booking in rows:
            classification = (
                payment.booking_application_reason
                or self.confirmation.reason(booking, payment)
                or PaymentApplicationReason.INVALID_BOOKING_STATE
            )
            result.append((payment, booking, classification))
        return result

    async def acknowledge(
        self,
        workspace_id: uuid.UUID,
        payment_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str,
    ) -> tuple[Payment, Booking]:
        try:
            booking_id = await self.session.scalar(
                select(Payment.booking_id).where(
                    Payment.workspace_id == workspace_id, Payment.id == payment_id
                )
            )
            if booking_id is None:
                raise NotFoundError("Booking payment not found")
            booking = await self.confirmation._lock_booking(workspace_id, booking_id)
            payment = await self.session.scalar(
                select(Payment)
                .where(Payment.workspace_id == workspace_id, Payment.id == payment_id)
                .with_for_update()
            )
            if payment is None or payment.booking_id != booking.id:
                raise NotFoundError("Booking payment not found")
            if (
                payment.booking_application_status
                != PaymentApplicationStatus.REQUIRES_REVIEW
            ):
                raise NotFoundError("Payment exception not found")
            if payment.booking_review_note != note:
                payment.booking_review_note = note
                payment.booking_reviewed_at = datetime.now(UTC)
                payment.booking_reviewed_by_user_id = actor_user_id
                self._event(
                    booking,
                    payment,
                    BookingEventType.PAYMENT_REVIEW_ACKNOWLEDGED,
                    actor_user_id,
                    {"reason": payment.booking_application_reason.value},
                )
            await self.session.commit()
            return payment, booking
        except Exception:
            await self.session.rollback()
            raise

    def _event(self, booking, payment, event_type, actor_user_id, extra):
        self.session.add(
            BookingEvent(
                workspace_id=booking.workspace_id,
                booking_id=booking.id,
                event_type=event_type,
                actor_type="HUMAN" if actor_user_id else "SYSTEM",
                actor_user_id=actor_user_id,
                event_metadata={"payment_id": str(payment.id), **extra},
            )
        )
