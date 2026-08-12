# AI context

## Product

- Name: **OneInFlow**
- Tagline: **Everything in one flow.**
- Category: **AI-first Customer Operations Platform**
- Customer explanation: manage customer conversations and the operational work
  that follows through AI and human collaboration.
- Stage: MVP; not production-ready.
- Primary market/language direction: Thailand and Thai-first UX.

OneInFlow is not documented as a general CRM replacement or as a sales-pipeline
product.

## Technical baseline

- Backend: FastAPI, async SQLAlchemy, Alembic, PostgreSQL, Redis, Qdrant.
- Frontend: Next.js, React, TypeScript.
- Sprint 9.1 operational routes: Overview, Inbox, Actions, Knowledge, Payments,
  Channels, Notifications, and Workspace/Settings.
- Overview is composed from existing APIs. There is no `/dashboard/overview`
  backend and no Sprint 9.1 migration.
- Analytics remains planned for Sprint 9.4.
- Actions has Queue and Action Types. Existing workspace-scoped
  `ActionDefinition` remains the server source of truth; owner/admin may mutate,
  members may read, keys are immutable, and lifecycle is enable/disable.
- PostgreSQL is authoritative; Qdrant is derived search data.
- Current Alembic head: `b8c9d0e1f2a3`.

## Implemented AI and operations rules

- `AUTO`/`COPILOT`: active Action Collection first, explicit supported Action
  intent second, grounded answering otherwise.
- `HUMAN`: no AI generation or Action Collection execution.
- AI/LLM output and retrieved Knowledge are untrusted.
- ActionRequest creation requires deterministic validation and explicit
  confirmation.
- Payment verification is independent; AI cannot mark a payment verified.
- Conversation-scoped client IDs make sequential and concurrent WebChat retries
  idempotent.
- Message JSONB contains safe result-recovery metadata only, never system
  prompts, full RAG context, vectors, secrets, or confirmation-token hashes.

## Human Handoff and notifications

- Exact supported customer phrases or an authenticated staff operation can move
  a conversation to `HUMAN`.
- Assignment accepts only an existing member of that workspace. Public WebChat
  cannot select an assignee.
- Return-to-AI is an authenticated explicit transition to `AUTO`.
- `needs_attention` is conversation-level; unread is separately derived per
  member from customer messages after their read cursor.
- Notification reads are isolated by workspace and recipient. Bodies omit full
  messages, Action payloads, slip data, and payment details.
- Active notification sources: handoff, assignment, new customer messages,
  Action creation/assignment, and verified Customer Payment.
- `PAYMENT_REVIEW_REQUIRED` is defined but has no active event source.

## Channel truth

- WebChat: **IMPLEMENTED**.
- LINE OA: **IMPLEMENTED** for text messaging.
- Facebook Page Messenger: **IMPLEMENTED** for text messaging.
- Instagram: **PLANNED LATER**, not Sprint 9.0.
- All three channels reuse the same orchestration core. External credentials are
  AES-GCM encrypted and external delivery is persisted truthfully.

## Billing truth

Customer Payment is an implemented foundation for money paid to a workspace
business. OneInFlow SaaS Billing, plans, entitlements, and quotas are planned for
Sprint 9.2. Production Slip Verification is planned for Sprint 9.3.
# SaaS billing context

Never infer capabilities from a plan key. Use `EntitlementService`. Authorization
and entitlement checks are independent. Do not treat Customer Payment as SaaS
billing, fabricate token usage, promise final Pricing v0.1, or expose self-upgrade.
