# Pilot Deployment and Operations Runbook

## Deployment (Ubuntu Server + Docker Compose)

1. Install supported Docker Engine and Compose plugin; configure host firewall so only SSH, HTTP and HTTPS are public.
2. Obtain the reviewed release. In `backend`, create `.env` from `.env.example`; set strong unique secrets and production provider credentials. Never commit it.
3. Set `APP_ENV=production`, `DEBUG=false`, explicit `CORS_ORIGINS`, `TRUSTED_HOSTS`, `NEXT_PUBLIC_API_URL`, production email/AI/embedding/EasySlip providers and a base64 32-byte channel encryption key.
4. Validate: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`.
5. Start dependencies: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres redis qdrant`.
6. Take and verify a database backup using `docs/17_BACKUP_RECOVERY.md`.
7. Run migrations as a controlled one-off: `docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm app alembic upgrade head`.
8. Start: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build app frontend`.
9. Check `/health`, then `/health/readiness`; inspect `docker compose logs --since 10m app frontend`.
10. Put Nginx/Cloudflare/a reviewed proxy in front of loopback ports. Terminate TLS, redirect HTTP to HTTPS and restrict request body sizes. Do not expose backend directly.
11. Configure HTTPS provider webhook URLs and run signed test events. Run Pilot flows below.

## Pilot onboarding

- Record Pilot expectations, consent and support contact; do not promise commercial SLA/legal guarantees.
- Review Knowledge content, Action Types, payment destination and authorized staff roles.
- Transfer channel credentials through an approved secret path; never chat/email/log them.
- Verify Workspace isolation with two test users, webhook connection ownership and entitlement behavior.
- Take a backup before every migration/update; record current image/commit and rollback owner.

## Smoke flows

Owner configures Knowledge, Action Type and channel. Customer asks a grounded question; citations resolve. An Action collects missing fields, requires confirmation, enters queue, assigns/starts/completes. Handoff enters HUMAN, notifies/assigns, allows staff reply, then returns AUTO. Payment evidence is verified through a fake provider boundary in automated tests. Analytics reflects activity. Entitlement denial preserves data. Demo creates no tenant records and enforces rate limit.

## Incident response

| Incident | Detect | Contain / recover | Verify |
|---|---|---|---|
| backend/frontend crash | health/logs | Compose restart; roll back reviewed image | probes and smoke login |
| PostgreSQL restart/loss | readiness/DB logs | stop writes; restore service or verified backup | Alembic current and query smoke |
| Redis loss | readiness, public 503 | restore Redis; never bypass limiter | Demo/WebChat/auth limited normally |
| Qdrant loss | readiness/search errors | recreate collection and re-index READY documents | grounded retrieval returns citations |
| bad migration | deploy failure | stop deploy; prefer forward fix; restore backup when incompatible | schema/Alembic plus tests |
| provider outage | normalized provider error | preserve state; manual retry only when idempotent | provider-specific smoke |
| channel disconnect | connection status/delivery | rotate/re-enter encrypted credentials and reconnect | signed inbound + outbound delivery |
| corrupt config | startup failure | compare secret checklist and last known config; rotate exposed secrets | startup/readiness |

Code rollback and database downgrade are separate decisions. Never blindly downgrade production data. Prefer forward-compatible code or restore the pre-deploy backup after impact review.
