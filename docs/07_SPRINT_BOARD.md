# Sprint board

Status is based on repository source, migrations, tests, and Git history rather
than the age of the original planning board.

## Completed foundation

- Authentication, email verification, password reset, users, and workspaces.
- Customers, conversations, messages, and WebChat sessions.
- Knowledge upload/extraction/chunking, embeddings, Qdrant indexing, semantic
  retrieval, RAG context, grounded generation, and citation validation.
- Action definitions, Action Collection, fulfillment queue, assignment,
  lifecycle, and audit events.
- Customer Payment foundation, evidence handling, and provider-neutral
  verification.

## Sprint 8.10 - COMPLETE

WebChat End-to-End AI Integration: grounded answers, citations, Action
Collection, explicit confirmation/cancellation, conversation-mode behavior, and
concurrency-safe message idempotency.

## Sprint 8.11 - COMPLETE

Human Handoff + Notifications: explicit customer/staff handoff, verified
workspace-member assignment, self-assignment/reassignment/unassignment, return
to AI, per-member read state, derived unread, conversation attention, in-app
notifications, and Action/verified Customer Payment notification sources.

## Sprint 9.0 - COMPLETE

LINE OA + Facebook Page Messenger Integration through a reusable Channel
Integration Layer. WebChat, LINE OA, and Facebook Page Messenger text messaging
are **IMPLEMENTED**. Instagram is not in Sprint 9.0.

## Subsequent planned sprints

- 9.1 - MVP Dashboard + Operational UX - **COMPLETE**
- 9.2 - SaaS Billing + Plans + Entitlements
- 9.3 - Production Slip Verification — IMPLEMENTED
- 9.4 - Analytics + Insights — IMPLEMENTED
- 9.5 - MVP Hardening + Pilot — COMPLETE
# Sprint 9.2 — SaaS Billing + Plans + Entitlements

Implementation complete pending final validation. Customer Payment remains a
separate domain. Pricing v0.1 is provisional and checkout is not implemented.
