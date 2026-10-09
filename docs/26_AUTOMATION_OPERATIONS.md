# Automation Operations Runbook

Sprint 10.6.1 makes the bounded Hotel Automation worker independently
supervisable. It does not add new triggers, actions, external queues, or a
general workflow engine.

## Runtime model

Run the API and worker as separate processes. The worker continuously polls
PostgreSQL in bounded batches, refreshes a persisted heartbeat, and uses
`FOR UPDATE SKIP LOCKED` when claiming outbox events, executions, and stale
executions. Multiple worker processes may run concurrently.

PostgreSQL event and execution handling has strong idempotency through unique
event, execution, and effect keys. External channel delivery remains an
at-least-once attempt model with provider deduplication only where the provider
supports it. OneInFlow does not claim exactly-once external delivery.

## Docker Compose

```bash
docker compose up -d postgres redis qdrant app automation-worker
docker compose ps
docker compose logs --tail=100 automation-worker
docker compose restart automation-worker
docker compose stop -t 30 automation-worker
```

The worker healthcheck executes:

```bash
python -m app.automation.worker --healthcheck
```

Exit code `0` means a RUNNING heartbeat is within the configured stale window.
No credentials or provider payloads are printed.

## systemd example for Ubuntu

```ini
[Unit]
Description=OneInFlow Automation Worker
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=oneinflow
Group=oneinflow
WorkingDirectory=/opt/oneinflow/backend
EnvironmentFile=/etc/oneinflow/backend.env
ExecStart=/opt/oneinflow/backend/.venv/bin/python -m app.automation.worker
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Install and operate it with:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now oneinflow-automation-worker
sudo systemctl status oneinflow-automation-worker
sudo journalctl -u oneinflow-automation-worker -n 100 --no-pager
sudo systemctl stop oneinflow-automation-worker
```

Keep the environment file readable only by the service account. Do not put
secrets in the unit file or command line.

## Configuration

| Setting | Default | Purpose |
| --- | ---: | --- |
| `AUTOMATION_WORKER_POLL_SECONDS` | 5 | Delay between bounded poll cycles |
| `AUTOMATION_WORKER_BATCH_SIZE` | 20 | Maximum rows claimed per phase |
| `AUTOMATION_WORKER_HEARTBEAT_SECONDS` | 15 | Heartbeat interval |
| `AUTOMATION_WORKER_STALE_SECONDS` | 45 | Worker stale threshold |
| `AUTOMATION_EXECUTION_STALE_SECONDS` | 300 | RUNNING recovery threshold |
| `AUTOMATION_BACKLOG_ALERT_THRESHOLD_SECONDS` | 300 | Oldest-pending alert threshold |
| `AUTOMATION_BACKLOG_ALERT_COUNT` | 1000 | Queue-count alert threshold |
| `AUTOMATION_WORKER_BUILD_IDENTIFIER` | empty | Optional deployment identifier |

Impossible values fail Settings validation at startup.

## Health and queue inspection

Owners and administrators can inspect the Automations operational panel or
call `GET /api/v1/automations/status` using their normal authenticated
workspace context. The response distinguishes `HEALTHY`, `STALE`, and
`NOT_RUNNING`, includes workspace queue counts and recent terminal failures,
and emits deterministic alert codes.

Important alerts are `WORKER_STALE`, `WORKER_NOT_RUNNING`,
`QUEUE_BACKLOG_HIGH`, `OLDEST_PENDING_TOO_OLD`,
`TERMINAL_FAILURES_PRESENT`, and `STALE_RUNNING_PRESENT`.

## Failed execution inspection and retry

Inspect the failure code and bounded failure history before retrying. An owner
or administrator may retry only a FAILED execution through
`POST /api/v1/automations/executions/{execution_id}/retry`. A successful,
running, scheduled, or cross-workspace execution is rejected. Manual retry
retains the same execution and effect key, preserves failure history, and
starts a new bounded attempt budget; it is not a force-execute endpoint.

For customer messages, an existing delivery row is never blindly resent. A
provider failure with an uncertain external outcome therefore remains visible
for operator investigation rather than claiming exactly-once delivery.

## Stale RUNNING recovery

When a worker crashes, another worker row-locks stale RUNNING executions in a
bounded batch. If attempt budget remains, it records `WORKER_INTERRUPTED` and
schedules the normal retry delay. Exhausted executions become terminal FAILED.
Concurrent recovery workers skip locked rows, so only one recovery transition
is applied. Fresh RUNNING work is not recovered.

## Troubleshooting

### Queue backlog

1. Check worker health and `last_successful_poll_at`.
2. Check `QUEUE_BACKLOG_HIGH` and `OLDEST_PENDING_TOO_OLD`.
3. Inspect worker logs for database connectivity or action error codes.
4. Add another identical worker process only after database health is known.
5. Do not increase batch size beyond the validated maximum of 500.

### Database connectivity failure

Verify PostgreSQL health and the worker's effective environment without
printing credentials. The worker logs a sanitized exception class, continues
bounded polling, and cannot update its heartbeat while PostgreSQL is down.
After connectivity returns, stale execution recovery handles abandoned work.

### Channel provider failure

Inspect the normalized delivery error and execution failure code. Never paste
tokens, payment evidence, or raw provider payloads into logs. Confirm provider
status before using the bounded manual retry action.

## Safe deployment and rollback

1. Back up PostgreSQL and run `alembic upgrade head` before starting the new worker.
2. Deploy the API and worker from the same build identifier.
3. Start one worker and confirm a healthy heartbeat and successful poll.
4. Confirm queue counts decrease before scaling beyond one worker.
5. Send SIGTERM and allow the configured graceful timeout during replacement.

Before downgrading the migration, stop all Automation workers. Downgrade removes
heartbeat and operations metadata but does not remove the underlying Sprint
10.6 automation definitions/events/executions. Roll back application and schema
together; never run the hardened worker against the older schema.
