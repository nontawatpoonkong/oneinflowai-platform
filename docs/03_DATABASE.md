# Database

PostgreSQL is the authoritative store. Current SQLAlchemy tables include:

- Identity and tenancy: `users`, `verification_challenges`,
  `password_reset_sessions`, `workspaces`, `workspace_members`.
- Customers and conversations: `customers`, `customer_identities`,
  `conversations`, `messages`, `webchat_sessions`,
  `conversation_read_states`, `notifications`, `channel_connections`,
  `channel_message_deliveries`.
- Knowledge: `knowledge_documents`, `knowledge_document_contents`,
  `knowledge_chunks`.
- Actions: `action_definitions`, `action_requests`, `action_events`,
  `action_collection_sessions`.
- Customer Payment: `payment_destinations`, `payments`, `payment_evidence`,
  `payment_verifications`.

Qdrant is not the source of truth. It stores derived knowledge vectors whose
workspace/document/chunk ownership is revalidated against PostgreSQL.

`workspaces.ai_instructions` is nullable bounded tenant configuration for AI
behavior and tone. It is not a document, chunk, vector, credential, or citation
source. A User may have zero or multiple `workspace_members` rows; registration
does not create either a Workspace or membership.

Sprint 10.9B adds `workspace_join_settings`, `workspace_access_requests`,
`workspace_member_capabilities`, and immutable `workspace_access_audit_events`.
Join settings store only a SHA-256 digest and short display hint, never the
plaintext code. A partial unique index enforces one `PENDING` request per
user/Workspace; member grants are unique by membership and capability.

## Conversation and WebChat idempotency

`conversations` stores status, channel, assignment, external identity, AI mode,
takeover timestamps, and the Sprint 8.11 fields `handoff_reason`,
`handoff_requested_at`, `assigned_at`, and `needs_attention`.

`messages.external_message_id` remains nullable for non-WebChat producers.
PostgreSQL enforces `UNIQUE (conversation_id, external_message_id)` while
allowing multiple NULL values. WebChat stores the customer `client_message_id`
there and identifies its assistant result as `assistant:<client_message_id>`.
The migration audits existing non-NULL pairs and stops if duplicates exist; it
does not rewrite history.

The existing JSONB `messages.metadata` stores only response reconstruction data
such as response type, citations, grounding state, collection ID, field status,
and confirmation summary. There is no second metadata column.

## Per-member read state

`conversation_read_states` contains `workspace_id`, `conversation_id`,
`user_id`, optional `last_read_message_id`, and `last_read_at`.
`uq_conversation_read_state_user` enforces
`UNIQUE (conversation_id, user_id)`. Unread count is derived from later customer
messages for that member; it is not persisted as a global unread boolean.

## Notifications

`notifications` contains workspace, recipient, controlled type, concise
title/body, entity type/id, read state/timestamp, and an optional deduplication
key. `uq_notification_recipient_deduplication` enforces:

```text
UNIQUE (workspace_id, recipient_user_id, deduplication_key)
```

PostgreSQL continues to allow multiple rows when the deduplication key is NULL.
Notification bodies do not copy full customer messages, Action payloads, slip
data, or complete payment details.

Defined notification types are `CONVERSATION_HANDOFF`,
`CONVERSATION_ASSIGNED`, `NEW_CUSTOMER_MESSAGE`, `ACTION_CREATED`,
`ACTION_ASSIGNED`, `PAYMENT_VERIFIED`, `PAYMENT_REVIEW_REQUIRED`, and
`WORKSPACE_ACCESS_REQUESTED`.
`PAYMENT_REVIEW_REQUIRED` is defined but has no active event source.

## Other important uniqueness boundaries

- `workspace_members`: one membership per `(workspace_id, user_id)`.
- `knowledge_chunks`: one `(content_id, chunk_index)` position.
- Action and Action Collection tables keep their model-defined workspace and
  idempotency constraints.
- Payment evidence and verification tables retain their model-defined duplicate
  protections; they are independent from OneInFlow SaaS Billing.

Sprint 9.3 requires no migration. Normalized EasySlip results fit the existing
`payment_verifications` fields, and provider attempts use the existing
`saas_usage_records` meter. Raw responses and full account details are not
persisted.

Sprint 9.4 adds no table or migration. Analytics aggregate existing source
tables and rely on their Workspace/status/date indexes. Query plans should be
measured before adding a conversation date/channel composite index.

## Sprint 9.0 channel schema

`channel_connections` is workspace-owned and unique by workspace, provider, and
external account. It stores only AES-GCM ciphertext, nonce, and key version.
`customer_identities` now has trusted workspace and connection links and
enforces `UNIQUE (channel_connection_id, external_user_id)`; legacy rows are
preserved with a NULL connection. `conversations.channel_connection_id` selects
the trusted outbound adapter.

`channel_message_deliveries` is unique by `message_id` and stores connection,
`PENDING`/`SENT`/`FAILED`, safe provider message ID, normalized error code, and
sent timestamp. It stores no raw provider response or credentials.

Sprint 10.9D adds `workspace_audit_events` and `product_usage_events` in revision
`8c9d0e1f2a3`. The audit table has a database trigger that rejects updates and
deletes. The usage table has a Workspace/user/event/navigation uniqueness key
for navigation idempotency. Both use Workspace/time indexes; they remain
separate because their semantics and future retention policies differ.

Current Alembic head is `0e1f2a3b4c5`.
# SaaS billing tables

- `saas_plans`: configurable plan and provisional pricing metadata
- `plan_entitlements`: boolean, limited, or unlimited capabilities
- `workspace_subscriptions`: period and lifecycle per Workspace
- `saas_usage_records`: append-only metered quantities

These tables are intentionally separate from `payments`, `payment_evidence`, and
`payment_verifications`, which represent end-customer payments.

## Rich Hotel catalog tables

Sprint 10.9C adds `hotel_room_type_beds`, `hotel_amenity_definitions`,
`hotel_room_type_amenities`, and `hotel_room_type_images`. Room types gain
guest-facing size, smoking, accessibility, highlight, and controlled-view
fields. Physical rooms gain building, wing, and internal notes. Image rows
store object references and accessible metadata only; active physical room
records remain the authoritative quantity.

## Sprint 10.9E promotion schema

Revision `9d0e1f2a3b4` adds `promotion_campaigns`, `promotions`,
`promotion_codes`, normalized property/room-type/rate-plan/source eligibility,
`booking_attributions`, and `promotion_redemptions`. Booking gains
`discount_amount` and a JSONB promotion snapshot while retaining its existing
subtotal/total/currency concepts. Composite Workspace foreign keys prevent
cross-tenant attribution and redemption links. One redemption per Booking and
one normalized code per Workspace are unique.

Sprint 10.9F revision `0e1f2a3b4c5` adds only `workspaces.status`, constrained
to `ACTIVE` or `SUSPENDED`, plus a status/created-time index. User lifecycle
reuses `users.is_active`; platform mutation accountability reuses the existing
nullable-Workspace, append-only audit ledger. No platform campaign, plan, or
secret-storage schema is introduced.
