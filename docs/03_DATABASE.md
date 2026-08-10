Customer

Conversation

Message

Knowledge

Embedding

Workspace

User

Message idempotency

- `messages.external_message_id` remains nullable for non-WebChat producers.
- PostgreSQL enforces uniqueness for `(conversation_id, external_message_id)`; multiple NULL values remain valid.
- A customer message stores `client_message_id`; its assistant result uses `assistant:<client_message_id>`.
- Existing JSONB `messages.metadata` stores safe response reconstruction data: response type, citations, grounding status, collection session ID, missing/invalid fields, and confirmation summary.
- No second metadata column or schema change to Payment, WebChatSession, Action, or ActionCollection was introduced.

The migration audits non-NULL legacy pairs before creating the constraint and
stops if duplicates exist. It never deletes, merges, or rewrites historical rows.

Sprint 8.11

- Conversation reuses `assigned_user_id`, `ai_mode`, and takeover timestamps; it adds controlled `handoff_reason`, `handoff_requested_at`, `assigned_at`, and `needs_attention`.
- `conversation_read_states` is unique by `(conversation_id, user_id)` and stores a per-member read cursor. Unread count is derived from later customer messages.
- `notifications` stores recipient, controlled type, concise title/body, entity reference, read state, and optional deduplication key.
- Notification deduplication is unique by `(workspace_id, recipient_user_id, deduplication_key)` while NULL remains allowed.
- Notification bodies never duplicate message text, action payloads, slip data, or complete payment details.
