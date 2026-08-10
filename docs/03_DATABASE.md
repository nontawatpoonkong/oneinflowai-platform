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
