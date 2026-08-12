# SaaS Billing, Plans, and Entitlements

Sprint 9.2 implements OneInFlow subscription foundations for a Workspace paying
OneInFlow. This is a separate domain from Customer Payment, where an end
customer pays a hotel, shop, clinic, or other Workspace business.

## Architecture

`SaaSPlan → PlanEntitlement → WorkspaceSubscription → EntitlementService → product service`

Plans are database rows with stable keys, display metadata, billing interval,
provisional price metadata, and entitlement rows. Entitlements use explicit
`BOOLEAN`, `LIMITED`, or `UNLIMITED` semantics. No sentinel number represents
unlimited access, and product services never interpret plan names.

Each Workspace has at most one effective `TRIALING`, `ACTIVE`, or `PAST_DUE`
subscription, enforced by a partial unique index. A subscription records its
own period boundaries so monthly usage follows the billing period rather than a
calendar month. Trial dates are supported, but no trial duration is promised.

## Usage and enforcement

Team members, Action Types, and Knowledge documents are derived directly from
their source tables. AI request and provider-reported token usage use append-only
`saas_usage_records`; missing provider token counts are never fabricated.

Count-based creation uses a PostgreSQL transaction advisory lock keyed by
Workspace and entitlement before recounting and inserting. This prevents
concurrent Action Type or future member-add operations from crossing limits.
Knowledge uploads use the same primitive. Channel creation and grounded AI are
checked server-side through the central service.

When a limit is reached, the default policy denies the operation with a
structured error. Overage can be represented but no monetary rate or automatic
charge exists. `PAST_DUE`, `CANCELED`, and `EXPIRED` restrict gated operations;
they never delete tenant data.

## Billing provider and pricing status

`BillingProvider` is provider-neutral. The development implementation cannot
create checkout or accept public billing events. No self-upgrade endpoint,
production checkout, webhook, or verified payment provider exists yet.

Pricing v0.1 (Starter ฿1,490, Growth ฿2,990, Business ฿5,990, Enterprise
custom) is seeded only as configurable reference data and remains a working
hypothesis. It is not final production pricing.

Authenticated read-only endpoints are:

- `GET /api/v1/billing/plans`
- `GET /api/v1/billing/subscription`
- `GET /api/v1/billing/entitlements`
- `GET /api/v1/billing/usage`

The Billing UI reflects these endpoints and truthfully states that checkout is
not configured.
