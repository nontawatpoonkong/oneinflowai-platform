# Hotel Automation Foundation

Sprint 10.6 adds a deliberately bounded automation runtime for authoritative Hotel events. It is not a general no-code workflow engine: definitions cannot contain code, arbitrary expressions, HTTP targets, loops, graphs, or AI-created rules.

## Durable architecture

Authoritative domain services insert a versioned `automation_domain_events` outbox row in the same PostgreSQL transaction as the Booking, Payment, Stay, Room, or Housekeeping transition. A manual worker (`python -m app.automation.worker`) claims bounded batches with `FOR UPDATE SKIP LOCKED`, evaluates active definitions in the same Workspace, creates one execution per definition/event, and runs due actions.

The first contract version supports these stable event names:

- `hotel.booking.confirmed`, `hotel.booking.cancelled`, `hotel.booking.expired`
- `hotel.payment.verified`, `hotel.payment.requires_review`
- `hotel.stay.created`, `hotel.stay.checked_in`, `hotel.stay.checked_out`, `hotel.stay.no_show`
- `hotel.room.dirty`, `hotel.housekeeping.completed`, `hotel.room.ready`

Payloads contain only bounded IDs, dates, amounts, currency, names needed by approved templates, and occurrence time. They never contain payment evidence, provider payloads, secrets, or credentials.

## Definitions and scheduling

Definitions are Workspace-scoped and disabled by default. Conditions accept only allowlisted fields and `EQ`, `NE`, `IN`, `GTE`, or `LTE`. Supported timing is `IMMEDIATE`, `DELAY_AFTER_EVENT`, `BEFORE_DATE_FIELD`, and `AFTER_DATE_FIELD`. Date-field scheduling combines the Hotel Property IANA timezone, an explicit local `HH:MM`, and a bounded offset before converting to UTC.

The preset API describes booking-confirmation, pre-arrival, payment-review, and post-stay examples. Presets never create or enable records automatically.

## Actions and templates

The code-owned action registry supports:

- `internal.notification`, reusing recipient-scoped Notification deduplication.
- `customer.message`, creating one Message with the execution effect key and dispatching through the trusted Conversation, ChannelConnection, CustomerIdentity, and `ChannelDeliveryService` boundary.

Customer messaging requires an existing external-channel Conversation. It does not call LINE or Facebook directly and fails closed when trusted channel context is absent. Templates are plain text replacements over an allowlist (`customer_name`, `booking_reference`, `check_in`, `check_out`, `property_name`, `currency`, and `total_amount`); Jinja statements, traversal, indexing, and unknown variables are rejected.

## Idempotency and retry

The outbox has a Workspace-scoped logical deduplication key. Executions are unique by automation/event and have a unique effect key. Notifications and Messages reuse that effect key, while channel deliveries remain unique per Message. Two workers cannot claim the same pending execution concurrently.

Retryable failures use bounded delays of 1, 5, then 15 minutes with at most three attempts. Validation and unsafe-context failures are terminal. External providers do not provide universal exactly-once delivery, so OneInFlow truthfully claims at-least-once processing with idempotent visible effects, not exactly-once delivery. An existing failed delivery is not silently resent.

## API and authorization

Workspace routes under `/api/v1/automations` provide validation, definitions, enable/disable, read-only presets, paginated execution history, and status counts. Owner/Admin have `automation.manage`; Members have `automation.read`. No endpoint runs an arbitrary execution.

## Operations and limitations

Run the worker as the separately supervised service documented in `26_AUTOMATION_OPERATIONS.md`. This sprint does not add Celery, Kafka, arbitrary webhook actions, PMS/OTA integrations, campaigns, billing automation, or AI authority. Operators can inspect worker health, pending/running/succeeded/failed counts, deterministic alerts, and safe error codes through the dashboard. Logs and APIs do not expose provider credentials or raw evidence.
