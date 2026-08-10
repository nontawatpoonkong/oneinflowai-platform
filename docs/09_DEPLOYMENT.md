Docker

↓

Ubuntu

↓

Nginx

↓

SSL

↓

Cloudflare

↓

Backup

WebChat AI configuration

- Configure generation, embedding, Qdrant, PostgreSQL, Redis, and security settings through environment variables.
- Development providers are deterministic local/test adapters, not production authorities.
- Apply Alembic migrations before traffic. The WebChat idempotency migration stops on conflicting legacy non-NULL message IDs.
- Back up PostgreSQL as the authoritative source; Qdrant is derived data.
- Never expose provider secrets, session tokens, confirmation-token hashes, prompts, or full RAG context.

Tests use isolated `oneflowai_test` through `TEST_DATABASE_URL`, never the normal application database.
