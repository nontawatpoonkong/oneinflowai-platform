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
`ACTION_ASSIGNED`, `PAYMENT_VERIFIED`, and `PAYMENT_REVIEW_REQUIRED`.
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

Current Alembic head is `b8c9d0e1f2a3`.
# SaaS billing tables

- `saas_plans`: configurable plan and provisional pricing metadata
- `plan_entitlements`: boolean, limited, or unlimited capabilities
- `workspace_subscriptions`: period and lifecycle per Workspace
- `saas_usage_records`: append-only metered quantities

These tables are intentionally separate from `payments`, `payment_evidence`, and
`payment_verifications`, which represent end-customer payments.
