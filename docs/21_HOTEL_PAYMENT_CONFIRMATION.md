# Hotel Payment Confirmation (Sprint 10.2)

Hotel Booking and Customer Payment remain separate bounded contexts. Payment owns slip evidence, provider verification, receiver matching, transaction-reference deduplication, and the `VERIFIED` decision. Booking owns the hold, immutable price snapshot, inventory reservation, and `CONFIRMED` transition. SaaS subscription billing is separate from both.

## Linkage and commands

An owner/admin advances a held booking to `PENDING_PAYMENT`, then calls `POST /api/v1/hotel/bookings/{booking_id}/payment` with a trusted workspace payment destination ID. The application service locks the booking, checks that its hold is live, and creates a customer Payment with the booking's snapshot `total_amount`, currency, customer/conversation context, and hold expiry. `payments.booking_id` is nullable for all existing non-Hotel payments. A composite `(workspace_id, booking_id)` foreign key enforces tenant scope. Repeating an active attempt returns that Payment; after a rejected/duplicate attempt, a new Payment can be linked without rewriting history. General Payment creation does not accept `booking_id` from a public request.

After the normal Payment verification path marks the linked Payment `VERIFIED`, reconciliation tries the Booking confirmation boundary and either applies the Payment or classifies it for staff review. An authorized owner/admin can retry through `POST /api/v1/hotel/bookings/{booking_id}/confirm-from-payment` with `payment_id`. This is an explicit, auditable domain operation, not a generic status PATCH or a provider/webhook mutation. AI cannot call it through an Action Definition.

## Confirmation transaction

The service locks the workspace-scoped Booking row, then the Payment row. It requires `PENDING_PAYMENT`, a live hold, a linked `VERIFIED` Payment in the same workspace, exact match of both expected and verified amount to the Booking snapshot, and exact currency match. It sets `booking_applied_at`, changes Booking to `CONFIRMED`, clears `hold_expires_at`, and appends one `BOOKING_CONFIRMED` event with only the Payment ID. One database commit applies these changes together; any failure rolls back all of them. Repeating confirmation with that same applied Payment returns the existing Booking and does not append another event.

`booking_applied_at` is the explicit single-use marker. A partial unique index permits sequential attempts but only one applied Payment per Booking; the Payment row itself can link to only one Booking. `PAYMENT_LINKED`, `REPLACEMENT_PAYMENT_LINKED`, `BOOKING_CONFIRMED`, and review events, plus existing PaymentVerification records, provide the audit trail. No slip image, raw provider response, credentials, or sensitive account details are copied to Booking events.

## Expiry and inventory

Booking row locking serializes confirmation with cancellation/expiry. The first valid transaction to obtain the lock determines the outcome: an already expired or cancelled Booking cannot be resurrected; a confirmed Booking cannot be expired. The actual confirmation checks wall-clock hold expiry *after* obtaining the lock. Payment verification does not extend a hold. If verification finishes too late, the Payment may be verified while the Booking cannot be confirmed; staff must resolve that exception manually. Confirmation does not reserve inventory again. The units reserved on `HELD` remain reserved for `CONFIRMED`; the existing expiry operation only releases `HELD` or `PENDING_PAYMENT` units.

## Scope and future seams

The MVP supports one successfully applied exact-amount Payment per Booking, with sequential replacement attempts after rejection. Partial/split/deposit payments, refunds, chargebacks, and cancellation of confirmed bookings are not implemented. The exception/reconciliation behavior is detailed in [Hotel Payment Reconciliation](22_HOTEL_PAYMENT_RECONCILIATION.md). Provider webhooks and AI output must not directly set Booking status.
