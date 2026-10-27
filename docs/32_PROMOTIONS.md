# Promotions, Discount Codes, and Attribution

Sprint 10.9E introduces a Workspace-scoped promotion foundation for hotel
Bookings. Promotion pricing is authoritative only inside the backend domain;
the frontend and AI never calculate or override a discount.

## Pricing boundary

- A quote or draft is informational and consumes no quota.
- Creating a Booking Hold revalidates the code against trusted property, room
  type, rate plan, stay dates, source, customer, subtotal, and currency.
- A successful Hold reserves quota and freezes `subtotal`, `discount_amount`,
  `total_amount`, and a safe promotion snapshot on the Booking.
- Campaign or rule changes after the Hold do not reprice that Booking.
- Cancellation or Hold expiry releases the reserved redemption. A new Hold
  must validate again.
- Payment uses the frozen discounted `Booking.total_amount`. Payment
  verification remains authoritative and cannot be changed by AI.

All arithmetic uses PostgreSQL `NUMERIC` and Python `Decimal`. Percentage
discounts round to two decimal places with `ROUND_HALF_UP`; maximum discounts
are applied when configured. A fixed discount requires matching currency, and
no discount may exceed the subtotal. Currency conversion is not implemented.

## Domain model

`PromotionCampaign` owns lifecycle and optional validity. `Promotion` contains
the deterministic discount and eligibility rule. `PromotionCode` provides a
case-insensitive customer code using the ASCII format `A-Z`, `0-9`, `-`, `_`.
`BookingAttribution` stores the controlled source and selected campaign/rule/
code. `PromotionRedemption` is unique per Booking and moves through
`RESERVED`, `CONFIRMED`, or `RELEASED`.

Campaign lifecycle:

```text
DRAFT -> ACTIVE <-> PAUSED
ACTIVE|PAUSED -> EXPIRED            (explicit or scheduled, Sprint 10.9F)
DRAFT|ACTIVE|PAUSED|EXPIRED -> ARCHIVED
```

Code lifecycle is `ACTIVE`, `DISABLED`, `EXHAUSTED`, `EXPIRED`, and
`ARCHIVED`. Records used by historical Bookings are not hard-deleted.

Workspace is part of the foreign-key scope for campaign, promotion, code,
customer, Booking attribution, and redemption relationships. The initial
release supports Workspace campaigns only; platform-wide execution is a future
extension seam.

## Eligibility and quota

Supported dimensions are property, room type, rate plan, source/channel, rule
validity, stay dates, minimum subtotal, currency, total usage, code usage, and
per-customer usage. Empty relation sets mean unrestricted for that dimension.
There is no expression language.

Validation returns safe reason codes such as `PROMOTION_NOT_FOUND`,
`PROMOTION_INACTIVE`, `PROMOTION_EXPIRED`,
`PROMOTION_SOURCE_NOT_ELIGIBLE`, `PROMOTION_MINIMUM_NOT_MET`,
`PROMOTION_USAGE_LIMIT_REACHED`, and
`PROMOTION_CUSTOMER_LIMIT_REACHED`.

Quota is reserved at Hold, not when a code is previewed. The service locks the
`PromotionCode` row, releases lapsed reservations of the rule, and then locks
its `Promotion` rule row before counting active reservations and confirmed
uses, so two competing Holds cannot consume the final use, even through
different codes of the same rule. The order code -> redemption -> rule matches
confirmation (redemption -> rule) and cancel/expiry (inventory -> redemption)
to avoid lock-order deadlocks.
A code `usage_limit` counts uses of that code only; a rule
`total_usage_limit` counts uses across every code of the rule; both must have
headroom. Catalog targets (properties, room types, rate plans) from another
Workspace or unknown IDs are rejected with `PROMOTION_TARGET_INVALID` (422)
before the composite foreign keys apply. Confirmation is idempotent;
cancel/expiry releases the reservation.

## Authorization and APIs

- `promotion.read`: list campaigns, rules, codes, redemptions, and validate.
- `promotion.manage`: create/update campaigns and rules and transition
  campaign/code lifecycle.
- Owners and admins receive both capabilities by role baseline. Members require
  explicit grants.

Routes are under `/api/v1/promotions`:

- `GET|POST /campaigns`, `GET|PATCH /campaigns/{id}`
- `POST /campaigns/{id}/activate|pause|expire|archive`
- `GET|POST /`, `PATCH /rules/{id}`
- `GET|POST /codes`, `POST /codes/{id}/enable|disable|archive`
- `POST /validate`
- `GET /redemptions`

Lifecycle transitions are idempotent toward their target: repeating one whose
target is already the current status (for example `pause` on a `PAUSED`
campaign or `disable` on a `DISABLED` code) returns `200` with the unchanged
resource, writes no audit event, and leaves `updated_at` untouched. This
matches the platform marketing API. A transition the state machine does not
allow from the current status (for example `pause` on an `ARCHIVED` campaign)
still returns `409 PROMOTION_TRANSITION_INVALID`.

The validation endpoint is a preview contract. Booking Hold never trusts its
subtotal or result and derives authoritative pricing again from hotel inventory
and rate-plan data.

## AI and UI

The read-only `validate_promotion_code` AI tool obtains Workspace, customer,
channel source, dates, catalog IDs, and price from trusted context. It returns
the service result. `create_booking_hold` accepts a code but performs a fresh
domain validation. AI has no tool that creates or edits promotions.

The Workspace Promotions screen provides dense Campaigns, Codes, and Usage
views plus structured rule configuration. Controls are capability-aware, while
the API remains the authorization authority. The current customer-facing code
entry is available through the AI booking flow, Booking APIs, and (since
Sprint 10.9F) the staff manual-booking composer at `/dashboard/bookings/new`.

## Analytics and audit

Analytics counts only confirmed redemptions linked to confirmed Bookings in
the selected redemption-time window. It reports gross subtotal, discount, net
total, and campaign/code/source usage. Every monetary dimension includes
currency; amounts in different currencies are never combined. These values are
performance measures, not ROI because campaign cost is not stored.

Lifecycle, rule/code changes, application, and redemption confirmation write
safe `WorkspaceAuditEvent` metadata. No prompt, credential, payment evidence,
or customer content is copied into promotion audit data.

## Known limitations

- Workspace campaigns only; no platform-wide or platform-funded execution.
  Platform operators may author drafts and reduce exposure (see
  [34_CAMPAIGN_OPERATIONS.md](34_CAMPAIGN_OPERATIONS.md)).
- Percentage and fixed amount only; no free-night or bundle rules.
- No currency conversion.
- Scheduled expiry/start runs in the automation worker (Sprint 10.9F); validity
  is still enforced at validation and Hold time regardless of the scheduler.
- No campaign-cost or ROI model.

Migration `9d0e1f2a3b4` introduced this foundation; Sprint 10.9F migration
`1f2a3b4c5d6` adds `management_origin`, `started_at`, and
`scheduled_job_states`.
