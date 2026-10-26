# PMS Adapter Foundation (Sprint 10.8)

Sprint 10.8 introduces a provider-neutral boundary for importing hotel
operational data from an external property management system (PMS). The
boundary is intentionally read-only: OneFlowAI never creates, edits, or
deletes records in an external PMS, and no AI tool can administer a PMS.

## Architecture and authority

Every adapter implements the typed `PMSProvider` contract and declares its
capabilities. Provider payloads are converted to strict normalized property,
room type, physical room, rate plan, inventory-day, and reservation contracts
before core services see them. Provider-specific JSON is not persisted.

Each connection uses `READ_ONLY_IMPORT` and selects one inventory authority:

- `LOCAL`: external inventory is compared with OneFlowAI but is not applied.
- `PMS`: mapped inventory may update the local daily total only after safety
  validation. It can never reduce inventory below locally reserved plus
  blocked units.

Rate plan prices are reconciliation-only in this sprint. A difference creates
an issue and does not overwrite the local commercial price. External
reservation application is deferred because the current Booking lifecycle
owns holds, payment, and confirmation semantics that an imported reservation
cannot safely imply.

## Connections and credentials

`PMSConnection` is Workspace-scoped and stores provider identity, active state,
mode, authority, cursor, and last sync outcome. Credentials are encrypted with
AES-256-GCM using the existing server-managed channel credential key and a
PMS-specific authenticated-data boundary. Plaintext credentials are accepted
only on create/update, never serialized, persisted, or logged.

The registry is explicit and has no dynamic import or fallback provider. The
deterministic fake adapter is used by automated tests and makes no network
request. A commercial provider adapter is not selected in Sprint 10.8.

## Explicit mappings

`PMSExternalMapping` maps `(connection, entity type, external ID)` to a local
Workspace entity. Property, room type, physical room, and rate plan mappings
are supported. Similar names and codes may inform staff, but the service never
silently fuzzy-matches them. Cross-Workspace local targets are rejected.

## Sync lifecycle, idempotency, and concurrency

A manual sync creates a durable `PMSSyncRun`, then fetches supported streams in
bounded pages and commits bounded work. The provider-neutral cursor advances
only after the entire safe run succeeds. Failed and partial runs do not advance
the durable connection checkpoint.

The database has a partial unique index that permits only one `PENDING` or
`RUNNING` run per connection. A racing request receives `PMS_SYNC_CONFLICT`
instead of executing duplicate provider work. Stable external mapping identity,
local inventory uniqueness, and open-issue uniqueness make repeated imports
idempotent.

The service owns a maximum of three attempts for explicitly retryable timeout,
rate-limit, and transient provider errors. Authentication, authorization, and
invalid-response errors fail immediately. Adapters do not hide retries.

## Reconciliation and inventory safety

Unmapped entities, rate differences, missing inventory mappings, local/PMS
inventory differences, and totals below local reservations are recorded as
bounded `PMSReconciliationIssue` rows. Issue details contain safe normalized
values only. No raw credentials or provider responses are stored.

For a mapped inventory day, the service locks the local row, evaluates
`reserved_units + blocked_units`, and refuses an external total below that
floor. Existing Booking, hold, Stay, and Housekeeping state is never deleted or
rewritten by the import.

## API and authorization

The Workspace-scoped API is under `/api/v1/pms`:

- providers and connections: list/create/read/update/test;
- `POST /connections/{id}/sync` for a bounded manual sync;
- mappings: list/create;
- sync runs: list/read;
- reconciliation issues: list.

Owner and Admin roles have `pms.manage`; members have read-only `pms.read`.
Every lookup derives tenancy from the authenticated Workspace, never from a
provider payload. The dashboard page at `/dashboard/hotel/pms` reflects the
backend state and provides no fake connected status.

## Scheduling and observability seam

The synchronous service boundary can be called later by a separately
supervised scheduler. This sprint does not add a queue or background worker.
Connection and run records expose last success/failure, timestamps, normalized
error code, fetched/applied totals, conflicts, warnings, and durable cursors.
Structured logs include Workspace, connection, provider, run, and bounded
counts but never credentials.

## Explicit limitations

- No PMS write-back or two-way synchronization.
- No reservation, availability, rate, check-in/out, housekeeping, or payment
  push to a PMS.
- No OTA/channel-manager integration or external webhook mutation.
- No production PMS vendor adapter or credential marketplace.
- No automatic mapping, AI conflict resolution, or AI PMS administration.
- No external reservation application to OneInFlowAI Booking in this sprint.

## Sprint 10.9C availability display

The availability calendar shows `PMS` only when the selected property has an
explicit mapping to an active PMS connection whose existing inventory
authority is `PMS`. It does not infer sync freshness or invent a stale warning
when the backend has no authoritative freshness contract.
