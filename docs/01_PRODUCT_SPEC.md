# Product specification

## Current milestone

Sprint 9.1, MVP Dashboard and Operational UX, is the latest
completed sprint.
OneInFlow remains an MVP-stage AI-first Customer Operations Platform.

## Implemented product baseline

### Identity and tenancy

- Registration, email verification, login, authenticated user lookup, and
  password-reset flows.
- Multi-tenant workspaces, workspace membership, and workspace isolation.
- Customers, channel identities, conversations, and persisted messages.

### WebChat

- Public visitor sessions are authorized by a scoped session token.
- WebChat resolves or creates the customer and conversation and persists turns.
- In `AUTO` and `COPILOT`, an active Action Collection is handled first, an
  explicit supported action intent can start collection, and other input uses
  grounded generation. `HUMAN` invokes neither AI nor Action Collection.
- Every send requires `client_message_id`. A conversation-scoped database
  constraint and race-safe claim/recovery flow prevent duplicate processing.
- Persisted assistant metadata supports safe recovery of grounded citations and
  Action Collection responses without storing prompts, full RAG context,
  vectors, secrets, or confirmation-token hashes.
- Explicit deterministic customer phrases can request human handoff. Fuzzy
  handoff intent and automatic handoff on grounding/provider failure are not
  implemented.

### Knowledge and grounded RAG

- Document upload, validated text extraction, deterministic bounded chunking,
  exact-text SHA-256 hashes, and transaction-safe rechunking.
- Provider-neutral embeddings, Qdrant indexing, workspace-filtered semantic
  retrieval, PostgreSQL ownership validation, bounded context assembly, and
  deterministic prompt packaging.
- Provider-neutral grounded generation, zero-knowledge short circuiting, and
  citation validation against trusted sources.

### Actions and fulfillment

- Workspace-owned `ActionDefinition`, `ActionRequest`, and `ActionEvent` data.
- Deterministic payload validation, idempotent Action creation, assignment,
  controlled lifecycle transitions, filtering, and audit history.
- AI-assisted multi-turn Action Collection with explicit confirmation or
  cancellation before an ActionRequest can be created.
- Fulfillment remains human/manual-first. External fulfillment API execution is
  not implemented.

### Customer Payment

- Workspace payment destinations, Customer Payment records, evidence upload,
  duplicate controls, provider-neutral slip verification, verification history,
  and optional Action linkage.
- The deterministic verification provider is for development/tests. The product
  does not claim authoritative production bank verification, supported banks,
  accuracy, or OCR-only verification.

### Human operations

- Controlled handoff reasons and explicit transitions to `HUMAN`.
- Assign-to-me, assignment to a verified WorkspaceMember, reassignment,
  unassignment, and explicit return to `AUTO`.
- `needs_attention` is conversation-level operational state.
- `ConversationReadState` stores a separate per-member cursor; unread counts are
  derived from customer messages after that cursor and are not a global boolean.
- Recipient-scoped in-app notifications, deduplication, notification bell, and
  inbox handoff/assignment/unread controls.
- Active notification sources: conversation handoff, conversation assignment,
  new customer message, Action creation, Action assignment, and verified
  Customer Payment.

## Current limitations

- WebChat, LINE OA, and Facebook Page Messenger text messaging are implemented.
- Instagram is planned later. Facebook Comments, Lead Ads, broadcasts, media
  messages, and advanced provider templates are not implemented.
- No email notification delivery, SMS, browser Web Push, mobile push, external
  notification channel, or background notification worker exists.
- No SaaS subscription billing, plan entitlement enforcement, or quota
  enforcement exists.
- No production slip-verification provider is claimed.
- Analytics is planned.

## Sprint 9.1 operational surface

The authenticated product exposes Overview, Inbox, Actions, Knowledge,
Payments, Channels, Notifications, and Workspace/Settings as the primary MVP
workflow. Overview composes existing resource APIs and does not introduce an
analytics or aggregate dashboard backend. Role-sensitive controls are hidden or
read-only in the client while server authorization remains authoritative.

Actions contains two concepts: the operational Queue and workspace-scoped
Action Types. An ActionDefinition specifies the ordered information AI may
collect. Collection still flows through deterministic server validation and
customer confirmation before an ActionRequest reaches the Queue. Owners and
admins may create, edit, enable, or disable definitions; members may view them.
Keys are immutable and deletion is not exposed.
- No fuzzy handoff classifier, grounding-failure auto-handoff, ML/team routing,
  or external fulfillment automation is implemented.

## Slip Verification entitlement requirement

- Plan 1: Slip Verification is not included.
- Plan 2+: Slip Verification is included with a monthly quota.

Sprint 9.2 is planned to define SaaS plans, entitlements, quota values, and the
subscription-policy response to quota exhaustion. Prices, quota amounts, and
commercial plan names are not defined here.

Customer Payment means money paid by a workspace's customer to that workspace.
OneInFlow SaaS Billing means a workspace paying OneInFlow for a subscription.
These are separate domains.
# Sprint 9.2 SaaS Billing

OneInFlow subscription billing is distinct from Workspace Customer Payment.
Workspaces receive data-driven plan entitlements and billing-period usage.
Pricing v0.1 remains a working hypothesis. No production checkout or free
self-upgrade exists.
