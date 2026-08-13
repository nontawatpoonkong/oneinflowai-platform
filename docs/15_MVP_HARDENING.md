# MVP Hardening and Pilot Readiness

OneInFlow is an MVP intended for a controlled Pilot, not commercial production certification.

Sprint 9.5 completion status: **MVP Complete — Pilot Ready**. The frontend
security baseline is Next.js 16.3.0, React 19.2.8 and next-intl 4.13.6 on
Node.js 20.9 or newer (the production container uses Node.js 22).

## Risk matrix

| Risk | Severity | Likelihood | Protection / Sprint 9.5 response | Deferred |
|---|---:|---:|---|---|
| Development AI in production Actions | P0 | High | Action adapters use configured Generation Provider, strict schema parsing, deterministic validation and explicit confirmation; production config fails closed | Provider-specific evals |
| Public AI/auth abuse | P1 | High | Redis atomic limits for Demo, WebChat and unauthenticated auth; Redis failure fails closed | Trusted-proxy network parser |
| Unsafe production secrets/origins | P0 | Medium | Startup validation rejects short secrets, wildcard CORS/hosts, debug and development providers | KMS/Vault |
| Public infrastructure ports | P1 | Medium | Production Compose removes PostgreSQL/Redis/Qdrant host ports; app/frontend bind loopback for reverse proxy | Network policy automation |
| Local evidence/Knowledge loss | P1 | Medium | Production storage volume and PostgreSQL backup/restore runbook | Object storage |
| Qdrant loss | P1 | Medium | PostgreSQL chunks remain authoritative; re-index each READY document | Automated bulk re-index job |
| Provider outage | P1 | Medium | Bounded timeouts, normalized errors and truthful persisted states | Automatic retries/background queues |
| Unbounded operational lists | P1 | Medium | Inbox, Actions, Knowledge paginate; Payments and verification history are bounded to 100/page | Unified cursor envelopes |

## Security invariants

- Workspace identity comes from authenticated membership or trusted ChannelConnection, never payload selection.
- AI output is untrusted. It cannot verify payments, bypass ActionDefinition validation, create an Action before confirmation, or alter entitlements.
- Knowledge context cannot override system instructions and citations are validated against supplied sources.
- Uploads enforce size, MIME/signature and generated storage keys; public responses do not expose storage paths or provider payloads.
- Provider credentials are encrypted at rest and omitted from API/log output. Secrets must be supplied by deployment environment.

## Public endpoints

Public surfaces are auth registration/login/recovery, Demo Chat, WebChat sessions/messages, signed LINE/Facebook webhooks, Facebook verification, liveness and readiness. Auth/WebChat/Demo are input-bounded and Redis-limited. Channel POSTs require signatures and a trusted connection id; duplicate inbound ids are idempotent. Health returns only concise dependency names and normalized state.

## Provider failure policy

| Dependency | Impact and preserved state | Readiness | Operator response |
|---|---|---|---|
| PostgreSQL | Writes fail/rollback; no authoritative operation | Unready | Restore service or database backup |
| Redis | Demo/WebChat/auth cost/abuse-sensitive requests return 503 | Unready | Restore Redis; do not bypass limiter |
| Qdrant | Knowledge retrieval unavailable; PostgreSQL chunks remain | Unready | Re-index READY documents |
| AI/embedding | Request fails safely; document state reports failure where applicable | Ready | Correct config/provider, retry manually |
| EasySlip | Payment returns to PENDING with ERROR verification; no auto retry | Ready | Retry manually after provider recovery |
| LINE/Facebook | Delivery records FAILED truthfully; no automatic retry | Ready | Inspect request id and retry manually if safe |
| Email | Registration/recovery state remains; delivery failure normalized | Ready | Restore provider and resend |

## Intentional limitations

Text-only LINE/Facebook; no Instagram, Facebook comments, Lead Ads, broadcast,
channel media/slips, read receipts, automatic outbound retry, worker queue,
KMS/Vault, production SaaS checkout provider, selected monitoring vendor, or
durable handoff event history. Pricing remains provisional. DPA, retention and
PDPA review is required before commercial launch. Direct socket IP is used for
rate limiting; the reverse proxy must prevent public backend access and pass
only a controlled source address.
