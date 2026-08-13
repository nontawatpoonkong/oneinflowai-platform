# MVP Release Checklist

- [ ] Reviewed commit/artifact and clean staged diff; tests, Ruff, frontend lint/type/build pass.
- [ ] One Alembic head; upgrade tested on empty DB and downgrade-one/upgrade tested in isolation.
- [ ] Custom-format PostgreSQL backup listed and restored into an isolated database.
- [ ] `APP_ENV=production`, debug off, explicit CORS/hosts and no localhost public URLs.
- [ ] Unique 32+ byte JWT/OTP secrets; DB, AI, embedding, email, EasySlip and channel credentials supplied outside Git/logs.
- [ ] Production providers selected; no development Action/generation/embedding/email/slip provider.
- [ ] PostgreSQL/Redis/Qdrant have persistent volumes and no public host ports.
- [ ] Frontend/backend reachable only through HTTPS reverse proxy; HTTP redirects to HTTPS.
- [ ] Liveness/readiness and Docker health are green; request-id structured logs are accessible.
- [ ] LINE/Facebook signed webhook and truthful outbound delivery smoke tests pass.
- [ ] Pilot Workspace Knowledge, Actions, roles, payment destination and entitlements reviewed.
- [ ] Demo/WebChat/auth rate limits and Redis fail-closed behavior verified.
- [ ] Rollback owner, previous artifact, backup path and support/escalation contacts recorded.
- [ ] MVP limitations and DPA/retention/compliance review acknowledged.

Passing this checklist permits **MVP Complete — Pilot Ready**, not Commercial Production Ready.
