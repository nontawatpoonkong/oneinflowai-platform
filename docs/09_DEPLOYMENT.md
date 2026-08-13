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

Handoff and notifications are synchronous PostgreSQL-backed foundations. No
external notification provider or background worker is required. Apply the
Sprint 8.11 migration before serving traffic and monitor API polling load; the
MVP frontend polls inbox and notifications rather than using WebSockets.

Set `CHANNEL_CREDENTIAL_ENCRYPTION_KEY` to a base64-encoded 32-byte server-only
key before configuring or using LINE/Facebook connections. Missing, malformed,
wrong-version, or authentication-failing keys fail channel operations closed
without preventing unrelated backend startup. Sprint 9.0 uses an
environment-managed `v1` key; KMS/Vault and automated rotation are not included.

Configure provider webhooks manually over HTTPS. Outbound `FAILED` state is
visible but has no automatic infinite retry worker. `SENT` records provider
acceptance only, not customer delivery/read.
# Sprint 9.5 production deployment

The authoritative Ubuntu/Docker Pilot procedure, secret checklist, HTTPS
boundary, migration sequence and rollback policy are in
`docs/16_PILOT_RUNBOOK.md`. Backup/restore commands and Qdrant recovery are in
`docs/17_BACKUP_RECOVERY.md`. Use the production Compose overlay; internal
PostgreSQL, Redis and Qdrant ports must not be published to the Internet.
The frontend requires Node.js 20.9 or newer; the supplied production Dockerfile
uses Node.js 22 and emits a Next.js standalone server.
