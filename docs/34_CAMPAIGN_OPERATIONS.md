# Campaign Operations, Staff Booking, and Lifecycle Scheduling

Sprint 10.9F builds on the Workspace promotion foundation
([32_PROMOTIONS.md](32_PROMOTIONS.md)) and the Platform Administration
Console ([33_PLATFORM_ADMIN_CONSOLE.md](33_PLATFORM_ADMIN_CONSOLE.md)). It adds
platform campaign governance, a staff manual-booking composer, supervised
scheduled lifecycle processing, and campaign analytics. Migration
`1f2a3b4c5d6` is additive and is the single Alembic head.

## Scope and funding semantics

The repository has no platform-funded discount, settlement, reimbursement, or
Workspace opt-in model. Therefore:

| Question | Answer in this release |
| --- | --- |
| Who owns a campaign? | Exactly one Workspace (`workspace_id` stays `NOT NULL`). |
| Who bears the discount? | The owning Workspace: it reduces that Workspace's hotel Booking revenue. |
| Is anything platform-funded? | No. `platform_funded=false` is returned on every campaign detail. |
| Can a code redeem in another Workspace? | No. Codes are unique and resolved per Workspace. |
| What does "platform campaign" mean? | A Workspace-owned campaign **authored** by a platform operator (`management_origin=PLATFORM`). It is not a funding statement. |

Because the platform does not pay for the discount, operators may only
**author drafts** and **reduce exposure**. They cannot activate, resume, or
re-enable a campaign/code: that decision belongs to the Workspace that bears
the cost. The API returns `PLATFORM_CAMPAIGN_ACTIVATION_REQUIRES_WORKSPACE`
for those targets and exposes no route for them.

**Business decision required to go further:** to support truly platform-wide or
platform-funded campaigns, OneInFlowAI must decide (1) the participation
model (Workspace opt-in per campaign, or contractual blanket consent), (2) the
funding split and settlement/reimbursement ledger, and (3) how the platform
share is represented in Booking snapshots, attribution, and analytics. Until a
domain model for those exists, platform campaigns must not be wired into
Booking pricing. A nullable `workspace_id` shortcut is explicitly rejected.

## Platform governance rules

All mutations require `User.is_platform_admin`, a reason (3–500 chars), and
`confirmed=true`. Every change delegates to `PromotionService` (the single
lifecycle authority) and writes a `WorkspaceAuditEvent` in the owning
Workspace with `actor_type=PLATFORM_ADMIN` and the reason in safe metadata.

| Operation | Allowed when |
| --- | --- |
| Create campaign | Target Workspace exists and is `ACTIVE`; created as `DRAFT`. |
| Edit name/description | Any non-archived status; Workspace `ACTIVE`. |
| Edit validity window | `DRAFT` only (live windows are locked for the platform); Workspace `ACTIVE`. |
| Add rule / code | `DRAFT` only; Workspace `ACTIVE`; catalog targets must belong to the same Workspace (composite FKs). |
| Pause | `ACTIVE` |
| Expire | `ACTIVE`, `PAUSED` |
| Archive | Any non-archived status |
| Disable / archive code | Per `CODE_TRANSITIONS` |
| Activate / resume / enable | Never (Workspace only) |

Authoring writes (create campaign, edit, add rule, add code) and catalog reads
require the owning Workspace to be `ACTIVE`; otherwise they return
`409 PLATFORM_CAMPAIGN_OPERATION_INVALID` (with `reason_code`
`WORKSPACE_NOT_ACTIVE` for edit, rule, code, and catalog) and write nothing.
Exposure-reducing operations (pause, expire, archive, disable or archive a
code) stay available for a `SUSPENDED` Workspace so operators can contain its
discounts. Campaign detail reflects this: for a non-active Workspace
`allowed_operations` omits `add_rule`/`add_code` and `editable_fields` is empty.

Repeating an operation that already reached its target is a no-op with no
duplicate audit event. The previous platform pause/archive path bypassed the
state machine (for example `ARCHIVED -> PAUSED`); it now delegates and returns
`PROMOTION_TRANSITION_INVALID`. Platform actions use the same domain action
names as Workspace actions (`PROMOTION_CAMPAIGN_PAUSED`, …) and are
distinguished by `actor_type`. Hard deletion is not offered; historical
redemptions and Booking price snapshots are never modified.

Workspace lifecycle additions: `POST /promotions/campaigns/{id}/expire` and
`POST /promotions/codes/{id}/enable` (`promotion.manage`). Activating a
campaign whose window already ended is rejected.

### Platform API (`/api/v1/platform/marketing`)

- `GET /campaigns?page&page_size<=100&workspace_id&status&origin&search`
- `POST /campaigns` · `GET|PATCH /campaigns/{id}`
- `POST /campaigns/{id}/rules` · `POST /campaigns/{id}/codes`
- `GET /campaigns/{id}/catalog?kind=property|room_type|rate_plan&page&page_size<=100&property_id&room_type_id&search&active_only=true`
  (read-only catalog targets, see below)
- `POST /campaigns/{id}/pause|expire|archive`
- `GET /codes?page&page_size&workspace_id&campaign_id&status&search` (prefix)
- `POST /codes/{id}/disable|archive`
- `GET /analytics?start&end` (timezone-aware, ≤ 366 days)
- `GET /lifecycle` (scheduler health)

Campaign detail returns funding semantics, allowed operations, editable
fields, rules with eligibility, codes with effective limit and remaining quota,
redemptions by status/currency, confirmed booking value by currency, and the
latest 50 audit events. `remaining` mirrors enforcement: the smaller headroom
of the code limit (this code's uses) and the rule total (all codes' uses).
Money in every `/platform/marketing/*` response, `/platform/analytics`, and
`/platform/marketing/attribution` is serialized as exact decimal strings.
Detail also returns `target_labels` (`{id: {name, active}}`) for the catalog
IDs its rules target.

### Catalog targets for platform-authored rules

`GET /campaigns/{id}/catalog` lets the console pick properties, room types,
and rate plans for a rule. The Workspace is always the campaign's owning
Workspace (no client `workspace_id`), so another Workspace's catalog is never
readable. Reads are allowed only while the campaign is `DRAFT` (the only state
in which rules can be added) and the owning Workspace is `ACTIVE`; otherwise
the API returns `409 PLATFORM_CAMPAIGN_OPERATION_INVALID` with `reason_code`
`CAMPAIGN_NOT_DRAFT` or `WORKSPACE_NOT_ACTIVE`, and the console hides the
picker for a non-active Workspace. It is paginated, ordered by name, searches name/code with escaped
wildcards, and hides inactive rows unless `active_only=false`; with `active_only=true` room types under an inactive property and rate plans under an inactive room type or property are hidden too (joined on the composite Workspace keys). `property_id`
filters room types and rate plans, `room_type_id` filters rate plans
(`PLATFORM_CATALOG_FILTER_INVALID` otherwise); a filter outside the Workspace
is 404. Rows contain only `id, kind, name, code, active, property_id,
room_type_id, currency` — no prices, descriptions, policies, inventory, or
guest data. The first read by an admin for a campaign writes
`PLATFORM_CATALOG_VIEWED` (`actor_type=PLATFORM_ADMIN`, area `PROMOTIONS`,
resource `HotelCatalog`, no resource ID so it stays out of the campaign trail)
in the owning Workspace with the campaign, kind, filters, page, returned
count, and `window_seconds=900`; the search text itself is not stored. Further
reads by the same admin for the same campaign within 15 minutes (paging,
searching, filtering, switching kinds) are covered by that event and are not
written again; a different admin, a different campaign, or a read after the
window writes a new event. An advisory lock keeps this exact under concurrent
reads, and audit rows are never updated. Rule creation still re-validates every target
(`PROMOTION_TARGET_INVALID`) and composite foreign keys remain the final guard.
The console fetches only after the operator opens "Target specific…",
debounces search, and blocks submission when a room type or rate plan sits
outside the selected parents.

## Staff manual booking composer

Route: `/dashboard/bookings/new` (navigation "New booking", capability
`booking.create`). The server also requires `room.read` for both
`POST /hotel/bookings/manual-quote` and `POST /hotel/bookings/hold`, matching
the catalog reads the composer needs; customer search requires `guest.read`
(a guest name may be entered instead). Stays are limited to 60 nights.

1. Choose property and dates, room type and rate plan, adults/children and
   room quantity. Field-level validation mirrors server rules.
2. Search an existing customer or enter a guest name.
3. Optionally apply a promotion code.
4. `POST /api/v1/hotel/bookings/manual-quote` returns a **non-authoritative**
   server quote: nightly rates, subtotal, discount, total, currency,
   availability (`RATE_CURRENCY_MISMATCH`, `OCCUPANCY_EXCEEDED`,
   `NOT_AVAILABLE`, `INSUFFICIENT_UNITS`), and promotion reason codes.
   `RATE_CURRENCY_MISMATCH` mirrors the Hold, which rejects a rate plan whose
   currency differs from its property, so the preview never reports a stay as
   available that the Hold would refuse. It locks nothing, reserves no inventory, and
   consumes no promotion quota. It uses the same availability service and
   `PromotionService.validate` (source `MANUAL`) that the Hold re-runs.
5. Explicit confirmation, then the existing `POST /hotel/bookings/hold` with a
   client idempotency key reused for retries of the same request. The Hold
   re-locks catalog and inventory rows, reprices, and revalidates the code.
6. The result shows the actual Booking state. A staff-created Booking is
   `HELD`, never `CONFIRMED`. With `booking.manage`, staff can move it to
   `PENDING_PAYMENT`; confirmation still requires verified payment through the
   existing payment boundary. `booking.cancel` allows cancelling the hold.

Attribution source is `MANUAL` (Booking `source=STAFF`). The `BOOKING_HELD`
audit event now carries `{quantity, source, promotion_applied}`.

## Scheduled lifecycle processing

The scheduler runs **inside the existing supervised automation worker**
(`python -m app.automation.worker`); there is no second process. Each poll
cycle, when the interval has elapsed, it runs one bounded transaction:

- `ACTIVE|PAUSED` campaigns with `valid_until <= now` → `EXPIRED`
  (audit `PROMOTION_CAMPAIGN_EXPIRED`, `actor_type=AUTOMATION`,
  `trigger=SCHEDULED`).
- `ACTIVE` campaigns with `started_at IS NULL` and `valid_from <= now` (window
  still open) → `started_at=now` (audit `PROMOTION_CAMPAIGN_STARTED`).

Rows are claimed with `FOR UPDATE SKIP LOCKED` and filtered by status, so
concurrent workers never transition or audit a campaign twice and a repeated
run is a no-op. A full batch triggers another batch on the next poll cycle;
a failure waits one interval. Timestamps are stored and compared in UTC.

The scheduler is not the source of eligibility truth: `PromotionService`
rejects codes outside campaign and rule windows at validation and Hold time
even if the scheduler is stopped. The migration back-fills `started_at` for
campaigns already active inside their window so no retroactive start events
are emitted.

| Setting | Default | Purpose |
| --- | ---: | --- |
| `PROMOTION_LIFECYCLE_ENABLED` | `true` | Run the phase in the worker |
| `PROMOTION_LIFECYCLE_INTERVAL_SECONDS` | 60 | 5–3600 |
| `PROMOTION_LIFECYCLE_BATCH_SIZE` | 100 | 1–500 per transition type |
| `PROMOTION_LIFECYCLE_STALE_SECONDS` | 300 | ≥ 2 intervals; health threshold |

### Health, failure, and recovery

State is kept in one bounded row of `scheduled_job_states`
(`promotion_campaign_lifecycle`): last start/success/failure, safe error code
(exception class or `AppError.code`, never messages or SQL), consecutive and
total failures, runs, and transitions applied. Health is exposed at
`GET /platform/marketing/lifecycle`, in `GET /platform/system/health`, and in
campaign analytics:

- `HEALTHY`, `DEGRADED` (recent failures), `STALE` (no success within the
  stale window), `NOT_RUNNING` (never succeeded).
- Alerts: `LIFECYCLE_NEVER_SUCCEEDED`, `LIFECYCLE_STALE`, `LIFECYCLE_FAILING`,
  `LIFECYCLE_BACKLOG` (campaigns overdue beyond the stale window).

Logs: `promotion.lifecycle.succeeded` (`expired`, `started`) and
`promotion.lifecycle.failed` (`error_code`).

Recovery: a failed batch rolls back completely, so restart or fix the cause
(usually database connectivity) and the next run processes the backlog. Check
worker health first (see [26_AUTOMATION_OPERATIONS.md](26_AUTOMATION_OPERATIONS.md)).
To pause scheduling during an incident set `PROMOTION_LIFECYCLE_ENABLED=false`
and restart the worker; validity enforcement remains in force. There is no
manual "run now" endpoint.

## Campaign analytics definitions

Workspace (`GET /analytics/overview`, `analytics.read`, own Workspace only)
adds to `sales.promotions`: `campaigns_by_status`, `codes_by_status`,
`reservation_funnel`, `daily_trend`, and `properties`. Platform analytics
(`GET /platform/marketing/analytics`) adds origin counts, top Workspaces, top
campaigns, source split, and scheduler health.

- **Reserved**: redemptions created at Hold time within the range, regardless
  of outcome. **Confirmed**: those now `CONFIRMED`. **Released**: `RELEASED`
  or a `RESERVED` row whose hold lapsed.
- **Confirmed metrics** (value, trend, top lists) count `CONFIRMED`
  redemptions of `CONFIRMED` Bookings by `redeemed_at` (UTC day buckets).
- **Gross** = Booking subtotal, **discount granted** = Booking discount, **net**
  = Booking total. Always grouped by currency; never summed across currencies.
- **Discount granted is not campaign cost.** No ROI, acquisition cost, or
  platform cost is reported; the response says so explicitly.
- **Validation attempts are unavailable**: preview validation is stateless and
  attempts are not persisted.
- Ranges must include a timezone and be at most 366 days. All queries are
  grouped SQL aggregates with bounded result lists.

## Known limitations

- No platform-funded or cross-Workspace campaign execution (business decision
  above).
- Platform catalog targeting is chosen per DRAFT rule only; existing rules are
  not re-targeted from the console. A target deactivated after rule creation
  keeps its rule; Workspace staff refine targeting.
- Code-level `EXPIRED`/`EXHAUSTED` statuses are not set by the scheduler;
  campaign expiry and quota checks already make such codes unusable.
- The composer was validated by API integration tests and type/lint/build
  checks, not by browser end-to-end tests.
- The lifecycle phase is covered by integration tests against PostgreSQL; it
  has not been exercised in a production deployment.
