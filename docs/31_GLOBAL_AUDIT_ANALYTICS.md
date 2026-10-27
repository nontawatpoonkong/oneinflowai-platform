# Global Audit, Product Usage, and Analytics

Sprint 10.9D adds two deliberately separate Workspace-scoped data systems.
`WorkspaceAuditEvent` is the append-only accountability view for meaningful
changes. `ProductUsageEvent` is bounded first-party navigation telemetry. They
do not share a table, lifecycle, or product meaning.

## Event boundaries

- A **Domain Event** records an authoritative business state transition, such
  as a Booking, Stay, or Housekeeping lifecycle change.
- An **Automation Event** is a durable trigger and execution record for a
  workflow.
- An **Audit Event** answers who or which trusted system performed a meaningful
  action, in which product area, on which resource, and with what result.
- A **Product Usage Event** answers which authenticated user viewed a product
  route. It is telemetry, not proof that a business action occurred there.

Existing Booking, Stay, Housekeeping, Billing, Automation, and AI Action event
histories remain authoritative. The global audit log stores only a small
cross-domain reference and safe metadata; it does not replace or copy their
payloads.

## Audit contract and immutability

`workspace_audit_events` records a trusted Workspace, optional actor user,
controlled actor type, action, controlled area, resource reference, optional
server route/method, result, request correlation ID, bounded safe metadata, and
timestamp. Normal product APIs expose read-only list/detail routes. ORM guards
and a PostgreSQL trigger reject UPDATE and DELETE operations.

The list endpoint is ordered by `occurred_at DESC, id DESC`, paginated, and can
filter by actor, action, area, resource type, result, date range, or bounded
search. `audit.read` is independent from `analytics.read`: owners/admins receive
the existing role baseline and a member needs an explicit grant.

Audit metadata is capped at 20 top-level fields and 4 KiB after JSON encoding.
Secret-shaped keys are rejected recursively. Passwords, OTPs, tokens,
credentials, payment evidence, bank payloads, card data, join-code plaintext,
AI prompts, customer message bodies, and document content must never enter the
audit row.

## Product usage and privacy

`product_usage_events` stores only authenticated Workspace/user identity,
optional browser-session UUID, navigation UUID, `PAGE_VIEW`, normalized
dashboard path, controlled feature, event time, and receive time. The client
cannot submit Workspace or user identity. One navigation UUID is idempotent;
moving away and returning is a new legitimate view.

The shared authenticated dashboard shell emits page views at route changes.
React re-renders do not emit duplicates, and ingestion failure is caught so it
cannot prevent the current page from rendering. The first implementation
accepts no extra event properties.

OneInFlowAI does not collect keystrokes, form contents, customer chat text,
payment details, clipboard data, mouse coordinates, DOM snapshots, screen
recordings, session replay, employee scores, hours-worked estimates, or
productivity rankings.

## Analytics contract

`GET /api/v1/analytics/overview` uses trusted Workspace context and requires
both `analytics.read` and the existing `analytics.basic` entitlement. The UTC
half-open range is bounded to 366 days. Aggregation uses grouped PostgreSQL
queries rather than a frontend N+1 loop or one-query-per-day loop.

The first-class Analytics view provides:

- Overview: confirmed bookings, Stay transition counts, payment exceptions,
  Home views, active users, conversation trend, and room readiness.
- Sales: lifecycle counts and confirmed value/average grouped by currency.
  Different currencies are never summed. Conversation and availability funnel
  stages are marked unsupported because precise attribution does not exist.
- Operations: check-in, check-out, and no-show transition events; current room
  readiness; Housekeeping completions; and average `ROOM_DIRTY` to `ROOM_READY`
  minutes for paired task events.
- AI and conversations: conversation counts, human handoffs, and safe AI tool
  action outcomes. Prompts, message bodies, hidden reasoning, and provider
  metadata are excluded.
- Automation: execution outcomes, retry/terminal counts, average attempts, and
  most-used definitions from existing execution history.
- Team and usage: page views, unique users, Home views, daily Home trend,
  feature usage, and a bounded recent Home-viewer table.

The UI offers Today, 7-day, 30-day, current-month, and custom range controls,
responsive tables, labeled bars, light/dark support, English/Thai copy, and the
current Cyan/Pink visual language. UTC is explicit in the API and calculation;
property-local reporting remains a future product decision rather than silently
using browser timezone.

## Performance and future seam

Both tables have Workspace/time indexes, with additional actor/action/area or
feature/user indexes. Live PostgreSQL aggregation is appropriate at the current
scale. The service/API boundary allows later materialized views, Timescale,
ClickHouse, or a warehouse without replacing the product contract. Those
systems are not part of this sprint.

## Retention and limitations

Audit data generally requires longer retention than usage telemetry, but legal,
commercial, and operational retention periods are not yet approved. No blind
deletion job is implemented. A later policy must define duration, export/legal
hold behavior, deletion authority, and aggregate preservation separately for
audit and usage data.

Current analytics are Workspace-level and UTC-based. There is no platform-wide
SaaS analytics, employee surveillance, generic query builder, data warehouse,
session replay, or fabricated attribution/occupancy metric.
