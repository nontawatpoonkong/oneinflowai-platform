# Roadmap

## Completed

### Sprint 8.10 - WebChat End-to-End AI Integration

- Grounded answers and validated citations.
- Action intent, multi-turn collection, confirmation, and cancellation.
- Conversation-mode routing and concurrency-safe message idempotency.

### Sprint 8.11 - Human Handoff + Notifications

- Explicit WebChat/staff handoff and return to AI.
- Workspace-member assignment, self-assignment, reassignment, and unassignment.
- Per-member read cursor and derived unread counts.
- Conversation attention state and recipient-scoped in-app notifications.
- Action and verified Customer Payment notification sources.

### Sprint 9.0 - LINE OA + Facebook Page Messenger Integration - COMPLETE

Reusable normalization, encrypted workspace connections, tenant-safe external
identity mapping, authenticated LINE/Facebook webhooks, shared
AI/Action/Handoff orchestration, text outbound dispatch, echo protection, and
truthful delivery state are implemented. Instagram is not part of Sprint 9.0.

### Sprint 9.1 - MVP Dashboard + Operational UX - COMPLETE

Implemented operational Overview, unified Inbox, Actions, Knowledge, Payments,
Channels, Notifications, and role-aware Workspace/Settings in English and Thai.
Overview reuses existing APIs; no aggregate dashboard endpoint or migration was
added. This does not mark Analytics as
implemented.

## Planned

### Sprint 9.2 - SaaS Billing + Plans + Entitlements

Planned OneInFlow subscription billing and entitlement/quota enforcement,
separate from Customer Payment. Product requirement: Plan 1 excludes Slip
Verification; Plan 2+ includes a monthly verification quota. Prices, quota
amounts, and quota-exceeded policy are not yet defined in implementation.

### Sprint 9.3 - Production Slip Verification

Implemented EasySlip API v2 integration, deterministic OneInFlow authority,
entitlement/quota enforcement, concurrency-safe usage reservation, sanitized
failures, Payment UX, tests, and documentation.

### Sprint 9.4 - Analytics + Insights

**IMPLEMENTED.** Workspace-scoped operational KPIs, daily conversation trends,
channel/handoff/Action/Customer Payment insights, current queue snapshot,
management authorization, entitlement enforcement, and EN/TH dashboard.

### Sprint 9.5 - MVP Hardening + Pilot

Planned security, observability, operational hardening, and pilot readiness.

## Later direction

Instagram, external notification delivery, and automated external fulfillment
remain later work unless assigned to a future sprint. No release date,
production SLA, pricing, or performance claim is established here.
# Sprint 9.2 — SaaS Billing foundation

Implemented: data-driven plans, Workspace subscriptions, central entitlements,
derived and metered usage, server-side quota checks, and truthful Billing UI.
Planned: verified production checkout/provider, webhook processing, finalized
prices/quotas, and monetary overage charging.
