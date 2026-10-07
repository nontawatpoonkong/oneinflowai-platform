# Hotel Payment Reconciliation (Sprint 10.2.1)

Financial verification and booking application are distinct. `Payment.status=VERIFIED` means the Payment domain accepted the slip; it does **not** guarantee `Booking.status=CONFIRMED`. Booking confirmation remains owned by `BookingPaymentConfirmationService`. The reconciliation service invokes that boundary or records a typed exception. It never forces a status, reserves inventory, creates a new Booking, or moves money.

## Application state and reasons

Booking-linked payments have `booking_application_status` (`UNAPPLIED`, `APPLIED`, `REQUIRES_REVIEW`), a typed `booking_application_reason`, and the existing `booking_applied_at` marker. Non-Hotel Payments leave application fields null. Reasons include expired/cancelled/already-confirmed Booking, amount or currency mismatch, link conflict, invalid Booking state, unverified Payment, and already-applied Payment. Legacy linked payments are backfilled from `booking_applied_at`; a verified-but-unapplied legacy Payment remains visible in the exception query even before a retry classifies it.

The verification service commits the Payment verdict first. For a linked `VERIFIED` Payment it then calls the Booking reconciliation boundary. With a live `PENDING_PAYMENT` Booking and exact snapshot amount/currency, reconciliation applies it in one Booking-first/Payment-second locked transaction. If the Booking is expired, cancelled, already confirmed with another Payment, or has a mismatched snapshot, it leaves the Payment financially `VERIFIED`, records `REQUIRES_REVIEW` and a machine-readable reason, and appends a `PAYMENT_REQUIRES_REVIEW` Booking event. Replaying the same verification or reconciliation request does not duplicate application or review events.

If the hold expires before the Payment is verified, inventory release remains owned by Booking expiry. A late verified Payment does not resurrect that Booking or reclaim its inventory. A hold whose wall-clock expiry passed but whose expiry batch has not yet run is also ineligible; the normal expiry operation must release its inventory.

## Replacement attempts

A rejected, duplicate, or expired Payment may be followed by a new attempt while the Booking still has a live `PENDING_PAYMENT` hold. Prior rows and verification records remain intact. Active or verified attempts cannot be silently replaced. The old `(workspace_id, booking_id)` uniqueness is replaced by a partial unique index on applied payments only. One Payment still links to at most one Booking; at most one Payment can be applied to a Booking. If two attempts later verify concurrently, the first valid application wins under the Booking lock; the second stays `VERIFIED` but requires review.

## Staff operations

- `GET /api/v1/hotel/payment-exceptions` lists up to 100 workspace-scoped verified-but-unapplied payments, with optional typed `reason` and `application_status` filters. Workspace members can read; no raw evidence, provider payload, full account number, or secret is returned.
- `POST /api/v1/hotel/payment-exceptions/{payment_id}/reconcile` retries safely. Owner/admin authorization is required.
- `POST /api/v1/hotel/payment-exceptions/{payment_id}/acknowledge` stores a bounded staff note and an immutable audit event. It does not change financial status or mark the exception financially resolved. Owner/admin authorization is required.
- `POST /api/v1/hotel/bookings/{booking_id}/confirm-from-payment` continues to use the same reconciliation/confirmation boundary and returns a typed reason on rejection. It cannot force-confirm.

The Payments dashboard shows the exception queue, reason, Booking/Payment identifiers, timestamp, and safe retry/review-note controls. Review acknowledgement is not a refund or payment application.

## Remaining operational seams

Refunds, external/manual settlement confirmation, chargebacks, partial or split payments, and automatic rebooking are not implemented. A paid guest whose Booking expired needs deliberate staff resolution; any new Booking must be created through the normal availability/hold flow. No direct database edit is needed to identify or acknowledge the exception, but this sprint does not implement money movement or close the financial obligation.
