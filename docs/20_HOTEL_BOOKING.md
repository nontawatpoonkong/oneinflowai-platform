# Sprint 10.1 — Hotel booking holds

The Hotel catalog and daily inventory from Sprint 10.0 remain authoritative. A booking hold is an authenticated owner/admin operation. The API is under `/api/v1/hotel/bookings`; reads and writes resolve the caller's workspace and enforce owner/admin membership. No AI write tool or payment callback can create or confirm a booking.

## State machine

| From | To | Operation |
| --- | --- | --- |
| DRAFT | HELD | Atomic hold creation, within one transaction |
| HELD | PENDING_PAYMENT | Explicit `advance-to-payment` operation before expiry |
| HELD or PENDING_PAYMENT | CANCELLED | Explicit `cancel` operation before expiry |
| HELD or PENDING_PAYMENT | EXPIRED | `expire` service operation after expiry |

`POST /bookings/draft` persists a draft without reserving inventory. `POST /bookings/{id}/hold` rechecks current catalog and inventory under locks, refreshes the draft's price/policy snapshot, and reserves the stay atomically. Direct `POST /bookings/hold` creates and activates a draft within one transaction. A draft can be cancelled without touching inventory. `CONFIRMED` is reserved for a later payment integration and cannot be set through this sprint's API. A terminal booking does not transition again; repeating cancellation or expiry of the same terminal state returns it without another inventory release or event. Other transitions return `BOOKING_TRANSITION_INVALID`.

## Hold and inventory accounting

The current hold policy is 15 minutes from creation, recorded as an absolute UTC `hold_expires_at`. At `now >= hold_expires_at`, a hold is expired, even in `PENDING_PAYMENT`. Explicit `POST /bookings/expire-due` runs a bounded batch. A future scheduler can call `BookingService.expire_due_holds`; no scheduler is required in this sprint. Expiry is not automatic on a clock tick, so stale holds continue to occupy `reserved_units` until the expiry operation runs. A retry with the same idempotency key returns the original booking, including its expired state.

Creation first locks the workspace/idempotency key with a PostgreSQL transaction advisory lock. It then locks the selected catalog rows and every inventory date in ascending date order using `SELECT FOR UPDATE`. Every night in `[check_in, check_out)` must exist and have at least the requested quantity available. Only then does one transaction insert the booking/item/events and increment each day's `reserved_units`. Any error rolls back all changes. Concurrent last-unit requests serialize on the inventory row; one succeeds and the other receives `BOOKING_UNAVAILABLE`. Expiry and cancellation lock the booking, then the same inventory rows, decrement once, and commit with the event.

The existing inventory management endpoint may still set manual reserved counts when no active booking overlaps a date. While a booking hold overlaps, that endpoint locks the row and rejects changes to its `reserved_units`, preventing an admin upsert from erasing an active reservation. Changes to total or blocked units remain subject to `reserved + blocked <= total`.

## Idempotency, snapshot, and scope

`(workspace_id, idempotency_key)` is unique. The SHA-256 fingerprint is computed from the canonical typed request and creation operation (draft or direct hold). An identical retry returns the existing booking without reserving again, even after a later state transition; a changed request or operation with the same key gets `BOOKING_CONFLICT`. The key and fingerprint are internal, not returned in the public booking response.

The booking holds property name, dates, occupancy, guest/customer/conversation link, currency, total and source. The single booking item holds quantity, room/rate names, nightly rate amounts, occupancy limits, refundable flag and cancellation policy. Money uses PostgreSQL `NUMERIC(12,2)` and Python `Decimal`. The subtotal is `nightly base price × nights × quantity`; taxes, fees, promotions and payment are outside this sprint. Reads use the saved snapshot, so editing a rate plan does not rewrite historical totals.

Composite database foreign keys enforce workspace ownership for property, customer, conversation, room type and rate plan; the service also validates links before creating a hold. A conversation must match the chosen customer. Audit events record type, actor and safe metadata; there is no secret or payment data in them.

## API and future boundary

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/hotel/bookings/hold` | Create or recover a hold |
| POST | `/api/v1/hotel/bookings/draft` | Create or recover a draft without inventory reservation |
| POST | `/api/v1/hotel/bookings/{id}/hold` | Refresh quote and activate a draft |
| GET | `/api/v1/hotel/bookings` | List workspace bookings |
| GET | `/api/v1/hotel/bookings/{id}` | Read saved snapshot and events |
| POST | `/api/v1/hotel/bookings/{id}/cancel` | Release active hold |
| POST | `/api/v1/hotel/bookings/{id}/advance-to-payment` | Enter pending payment without confirming |
| POST | `/api/v1/hotel/bookings/expire-due` | Release expired holds in a bounded batch |

AI may search availability through the existing read-only tool. A future customer-facing booking action must use explicit customer confirmation before calling the hold service; it cannot call this staff API silently. Future payment integration seam: verified payment plus a still-valid `PENDING_PAYMENT` booking may be evaluated by a separate `BookingConfirmationService`, with its own transactional checks, to enter `CONFIRMED`. No such transition, payment coupling, refund, check-in/out, PMS/OTA sync, room assignment or ledger is implemented here.
