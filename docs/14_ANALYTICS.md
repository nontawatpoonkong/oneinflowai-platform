# Analytics and Insights

Sprint 9.4 derives management analytics directly from Workspace-scoped
PostgreSQL source tables. There is no analytics fact table, warehouse, ETL,
event stream, Redis cache, or predictive model.

## Access and range

`GET /api/v1/analytics/overview?start=<ISO-8601>&end=<ISO-8601>` requires an
authenticated Workspace owner/admin and the `analytics.basic` entitlement.
Members and public/demo callers are denied. Both boundaries must include a
timezone, are normalized to UTC, and use a half-open interval `[start, end)`.
The maximum range is 366 days. Daily buckets are UTC dates and missing dates
are returned as zero.

## Metric definitions

- **Unique customers**: distinct `Conversation.customer_id` among conversations
  created in the range.
- **Conversations**: conversations created in the range.
- **Customer/AI/staff messages**: messages created in the range, joined through
  a Workspace-owned conversation and grouped by trusted sender type.
- **AI-handled rate**: conversations created in the range that contain at least
  one AI message and have no recorded `handoff_requested_at`, divided by all
  conversations created in the range. It is not resolution, accuracy, success,
  conversion, or customer satisfaction.
- **Handoff rate**: conversations whose current recorded handoff timestamp is in
  the range divided by conversations created in the range. The schema retains
  the latest/current handoff fields, not a complete handoff event history.
- **Action completion rate**: Actions created in the range whose current status
  is `COMPLETED`, divided by Actions created in the range.
- **Payment verification rate**: Customer Payments created in the range whose
  current status is `VERIFIED`, divided by Customer Payments created in the
  range. SaaS subscriptions are separate tables and never included.
- **Verified amount**: sum of `verified_amount` for verified Customer Payments
  created in the range, grouped by currency. Currencies are never combined.
- **Slip verification status**: `PaymentVerification` attempts created in the
  range grouped by normalized status. No evidence, account, credential, raw
  response, or message content is returned.

## Current queue snapshot

Open/unassigned Actions and conversations needing attention are current state,
not historical range metrics. The UI labels this section `Current`.

## Performance and limitations

Queries aggregate in PostgreSQL, always filter by Workspace, and never load raw
messages into Python. Existing Workspace/status/date indexes cover the MVP query
shape adequately; no Sprint 9.4 migration is required. Conversation date and
channel do not yet have a composite analytics index; measure production query
plans before adding one. The MVP does not provide attribution, forecasting,
semantic quality, AI accuracy, accounting, comparison periods, or full event
history.
