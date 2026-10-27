# OneInFlowAI Platform Administration Console

Sprint 10.9F introduces a dedicated internal control plane at `/platform` and
`/api/v1/platform`. It is not a Workspace administration surface. Every API in
the namespace requires an authenticated `User.is_platform_admin == true`;
Workspace roles and capabilities never grant platform access. The service and
dependency boundary is intentionally small so future platform roles can replace
the boolean gate without weakening cross-tenant query authorization.

## Bounded operator capabilities

The console provides paginated global Users, Workspaces, subscriptions,
Workspace campaigns, promotion codes, attribution, and immutable audit views.
It also provides truthful aggregate analytics and read-only AI, automation,
PMS, channel, queue, and database health. Responses exclude password hashes,
tokens, credentials, payment evidence, prompts, customer message content, and
model hidden reasoning. There is no SQL editor, arbitrary JSON editor,
impersonation, secret editor, or generic domain-state bypass.

High-impact mutations require explicit confirmation and a non-empty reason.
Supported actions are limited to User suspension/reactivation, Workspace
suspension/reactivation, existing Pilot subscription activation, campaign
pause/archive, and promotion-code disable/archive. They use existing domain
state machines where one exists and append `PLATFORM_ADMIN` audit events.
Historical Booking price snapshots, redemption rows, and audit rows remain
immutable.

## Lifecycle semantics

User `ACTIVE/SUSPENDED` maps to the existing `User.is_active` authority. A
suspended user cannot log in and an already-issued token fails on the next
authenticated request because the database user is resolved each time. Platform
administrators cannot suspend themselves through this API. Platform-admin
promotion or demotion is deliberately not exposed.

Workspace `ACTIVE/SUSPENDED` is explicit persisted state. Suspension blocks
member operational resolution, capability checks, new public WebChat activity,
provider webhook ingestion, and new automation event/execution claims. It does
not delete data, rewrite history, or mutate hotel domain state. Reactivation
restores those entry points. Existing in-flight external side effects cannot be
recalled; operators must investigate their authoritative domain records.

## Catalog and marketing authority

The current Plan catalog is deterministically code-seeded by
`EntitlementService.ensure_reference_catalog`. The Platform console therefore
shows Plans and entitlements as read-only. CRUD is deferred until OneInFlowAI
chooses a single durable product-catalog authority.

Promotions remain Workspace-owned. Since Sprint 10.9F platform operators can
search and inspect campaigns and codes, author DRAFT campaigns/rules/codes
inside a Workspace, and pause/expire/archive campaigns or disable/archive
codes. Every mutation delegates to the promotion state machine and is audited
with a reason; activation, resume, and re-enable stay with the Workspace. See
[34_CAMPAIGN_OPERATIONS.md](34_CAMPAIGN_OPERATIONS.md). Platform campaign
execution is deferred: the current schema has no explicit Workspace opt-in or
settlement/reimbursement authority, so no nullable-Workspace shortcut or silent
cross-hotel discount is permitted. The attribution view groups hotel Booking
gross value, discount, and net value by Workspace, campaign/code, source, and
currency. It is not labelled ROI because campaign cost is unavailable.

## Analytics definitions

DAU, WAU, and MAU are unique authenticated users with accepted `PAGE_VIEW`
events in rolling 1-, 7-, and 30-day UTC windows. Feature use and active
Workspace data come from persisted product events. Hotel Booking Value is
grouped by currency. It is never presented as OneInFlowAI SaaS revenue. Manual
subscription activation is not payment; SaaS revenue remains unavailable until
an authoritative subscription-payment ledger exists.

## Known limitations and future seams

- Subscription cancel/expire and trial-start actions remain unavailable because
  the current billing service exposes only safe Pilot activation.
- Platform campaign execution requires explicit participation plus a funding or
  settlement policy.
- Plan mutation requires one product-catalog authority and history-safe archive
  semantics.
- Infrastructure health is limited to persisted/authoritative signals already
  available to the application; it does not invent provider online status.
- Future platform roles should split support, finance, operations, read-only,
  and super-admin authority inside the dedicated platform dependency/service
  layer.
- Feature flags, legal deletion workflows, and account impersonation are out of
  scope.
