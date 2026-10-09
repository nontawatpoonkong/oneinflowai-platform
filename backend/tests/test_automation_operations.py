"""PostgreSQL-backed Automation operations hardening tests."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

import app.automation.worker as worker_module
import app.services.automation as automation_service_module
from app.core.config import Settings
from app.models.automation import (
    AutomationDefinition,
    AutomationExecution,
    AutomationWorkerHeartbeat,
    AutomationWorkerState,
    DomainEventOutbox,
)
from app.models.notification import Notification
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.automation import MAX_ATTEMPTS, AutomationService
from tests.conftest import TestSessionLocal
from tests.test_automation import _account, _headers


async def _seed(
    workspace_id,
    *,
    status="PENDING",
    attempt=0,
    started=None,
    scheduled=None,
    terminal=False,
    action="internal.notification",
    payload=None,
):
    async with TestSessionLocal() as session:
        definition = AutomationDefinition(
            workspace_id=workspace_id,
            name="Ops",
            active=True,
            trigger_event_type="hotel.payment.requires_review",
            trigger_version=1,
            conditions=[],
            action_type=action,
            action_config={"title": "Review", "body": "Review {{currency}}"},
            schedule_mode="IMMEDIATE",
            schedule_config={},
        )
        session.add(definition)
        await session.flush()
        event = DomainEventOutbox(
            workspace_id=workspace_id,
            aggregate_type="payment",
            aggregate_id=uuid.uuid4(),
            event_type="hotel.payment.requires_review",
            event_version=1,
            payload=payload or {"currency": "THB"},
            occurred_at=datetime.now(UTC),
            available_at=datetime.now(UTC),
            state="PROCESSED",
            attempt_count=1,
            processed_at=datetime.now(UTC),
            deduplication_key=f"ops:{uuid.uuid4()}",
        )
        session.add(event)
        await session.flush()
        execution = AutomationExecution(
            workspace_id=workspace_id,
            automation_id=definition.id,
            event_id=event.id,
            status=status,
            scheduled_for=scheduled or datetime.now(UTC),
            started_at=started,
            completed_at=datetime.now(UTC)
            if status in {"FAILED", "SUCCEEDED"}
            else None,
            attempt_count=attempt,
            terminal_failure=terminal,
            last_error_code="TEST_FAILURE" if status == "FAILED" else None,
            effect_key=f"automation:{definition.id}:{event.id}",
        )
        session.add(execution)
        await session.commit()
        return execution.id


def _settings(**overrides):
    values = {
        "AUTOMATION_WORKER_POLL_SECONDS": 0.05,
        "AUTOMATION_WORKER_BATCH_SIZE": 2,
        "AUTOMATION_WORKER_HEARTBEAT_SECONDS": 0.05,
        "AUTOMATION_WORKER_STALE_SECONDS": 1,
        "AUTOMATION_EXECUTION_STALE_SECONDS": 60,
        "AUTOMATION_BACKLOG_ALERT_THRESHOLD_SECONDS": 60,
        "AUTOMATION_BACKLOG_ALERT_COUNT": 2,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"AUTOMATION_WORKER_POLL_SECONDS": 0},
        {"AUTOMATION_WORKER_BATCH_SIZE": 0},
        {"AUTOMATION_WORKER_BATCH_SIZE": 501},
        {"AUTOMATION_WORKER_HEARTBEAT_SECONDS": 0},
        {"AUTOMATION_WORKER_STALE_SECONDS": 0},
        {"AUTOMATION_EXECUTION_STALE_SECONDS": 0},
        {"AUTOMATION_BACKLOG_ALERT_THRESHOLD_SECONDS": 0},
        {"AUTOMATION_BACKLOG_ALERT_COUNT": 0},
    ],
)
def test_worker_settings_reject_impossible_values(overrides):
    with pytest.raises(ValidationError):
        _settings(**overrides)


def test_worker_startup_bounded_poll_heartbeat_and_shutdown(client_db, monkeypatch):
    calls = []

    async def fake_run_once(self, **kwargs):
        calls.append(kwargs)
        return 1, 1

    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(AutomationService, "run_once", fake_run_once)
    asyncio.run(
        worker_module.run_worker(
            settings=_settings(), worker_id="worker-test", max_cycles=1
        )
    )
    assert calls[0]["batch_size"] == 2

    async def verify():
        async with TestSessionLocal() as session:
            row = await session.scalar(select(AutomationWorkerHeartbeat))
            assert row.state == AutomationWorkerState.STOPPED.value
            assert row.last_successful_poll_at is not None

    asyncio.run(verify())


def test_graceful_stop_releases_bounded_claims(client_db):
    account, _ = _account(client_db, "worker-stop")
    workspace_id = uuid.UUID(account["workspace"]["id"])
    ids = [asyncio.run(_seed(workspace_id)) for _ in range(3)]

    async def scenario():
        stop = asyncio.Event()
        stop.set()
        async with TestSessionLocal() as session:
            assert (
                await AutomationService(session).run_executions(
                    batch_size=2, worker_id="stopping", stop_event=stop
                )
                == 0
            )
        async with TestSessionLocal() as session:
            rows = list(
                await session.scalars(
                    select(AutomationExecution).where(AutomationExecution.id.in_(ids))
                )
            )
            assert sum(row.status == "PENDING" for row in rows) == 3
            assert all(row.claimed_by_worker_id is None for row in rows)
            assert all(row.attempt_count == 0 for row in rows)

    asyncio.run(scenario())


def test_stale_recovery_is_locked_bounded_and_terminal_when_exhausted(client_db):
    account, _ = _account(client_db, "stale")
    workspace_id = uuid.UUID(account["workspace"]["id"])
    now = datetime.now(UTC)
    fresh = asyncio.run(
        _seed(
            workspace_id,
            status="RUNNING",
            attempt=1,
            started=now - timedelta(seconds=10),
        )
    )
    retry = asyncio.run(
        _seed(
            workspace_id,
            status="RUNNING",
            attempt=1,
            started=now - timedelta(minutes=2),
        )
    )
    terminal = asyncio.run(
        _seed(
            workspace_id,
            status="RUNNING",
            attempt=MAX_ATTEMPTS,
            started=now - timedelta(minutes=2),
        )
    )

    async def recover(worker):
        async with TestSessionLocal() as session:
            return await AutomationService(session).recover_stale_executions(
                stale_seconds=60, batch_size=10, now=now, worker_id=worker
            )

    async def scenario():
        counts = await asyncio.gather(recover("b"), recover("c"))
        assert sum(counts) == 2
        async with TestSessionLocal() as session:
            fresh_row = await session.get(AutomationExecution, fresh)
            retry_row = await session.get(AutomationExecution, retry)
            terminal_row = await session.get(AutomationExecution, terminal)
            assert fresh_row.status == "RUNNING"
            assert retry_row.status == "PENDING"
            assert retry_row.scheduled_for == now + timedelta(seconds=60)
            assert len(retry_row.failure_history) == 1
            assert terminal_row.status == "FAILED"
            assert terminal_row.terminal_failure is True

    asyncio.run(scenario())


def test_status_metrics_alerts_and_authorization_are_workspace_scoped(
    client_db, monkeypatch
):
    owner, token = _account(client_db, "status")
    other, _ = _account(client_db, "status-other")
    workspace_id = uuid.UUID(owner["workspace"]["id"])
    now = datetime.now(UTC)
    asyncio.run(_seed(workspace_id, scheduled=now - timedelta(minutes=5)))
    asyncio.run(_seed(workspace_id, scheduled=now + timedelta(hours=1)))
    asyncio.run(
        _seed(
            workspace_id,
            status="RUNNING",
            attempt=1,
            started=now - timedelta(minutes=2),
        )
    )
    asyncio.run(
        _seed(workspace_id, status="FAILED", attempt=MAX_ATTEMPTS, terminal=True)
    )
    asyncio.run(_seed(uuid.UUID(other["workspace"]["id"])))

    async def heartbeat():
        async with TestSessionLocal() as session:
            await AutomationService(session).record_worker_heartbeat(
                "stale-worker",
                AutomationWorkerState.RUNNING,
                now=now - timedelta(minutes=2),
            )

    asyncio.run(heartbeat())
    monkeypatch.setattr(automation_service_module, "get_settings", _settings)
    response = client_db.get("/api/v1/automations/status", headers=_headers(token))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["worker"]["health"] == "STALE"
    assert data["queue"] | {} == data["queue"]
    assert (
        data["queue"]["pending"],
        data["queue"]["scheduled"],
        data["queue"]["running"],
    ) == (1, 1, 1)
    assert data["queue"]["terminal_failed"] == 1
    assert data["oldest_pending_age_seconds"] >= 299
    assert set(data["alerts"]) >= {
        "WORKER_STALE",
        "QUEUE_BACKLOG_HIGH",
        "OLDEST_PENDING_TOO_OLD",
        "TERMINAL_FAILURES_PRESENT",
        "STALE_RUNNING_PRESENT",
    }

    async def member():
        async with TestSessionLocal() as session:
            row = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == uuid.UUID(owner["user"]["id"]),
                )
            )
            row.role = WorkspaceRole.MEMBER
            await session.commit()

    asyncio.run(member())
    assert (
        client_db.get("/api/v1/automations/status", headers=_headers(token)).status_code
        == 403
    )


def test_manual_retry_state_auth_scope_and_idempotent_effect(client_db):
    owner, token = _account(client_db, "manual")
    _, other_token = _account(client_db, "manual-other")
    workspace_id = uuid.UUID(owner["workspace"]["id"])
    execution_id = asyncio.run(_seed(workspace_id))

    async def run_and_mark_failed():
        async with TestSessionLocal() as session:
            await AutomationService(session).run_executions(batch_size=1)
        async with TestSessionLocal() as session:
            row = await session.get(AutomationExecution, execution_id)
            effect_key = row.effect_key
            row.status = "FAILED"
            row.terminal_failure = True
            row.completed_at = datetime.now(UTC)
            row.last_error_code = "REVIEW"
            row.failure_history = [
                {
                    "error_code": "REVIEW",
                    "attempt": 1,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "source": "test",
                }
            ]
            await session.commit()
            assert await session.scalar(select(func.count(Notification.id))) == 1
            return effect_key

    effect_key = asyncio.run(run_and_mark_failed())
    response = client_db.post(
        f"/api/v1/automations/executions/{execution_id}/retry", headers=_headers(token)
    )
    assert response.status_code == 200
    assert response.json()["data"]["manual_retry_count"] == 1
    assert (
        client_db.post(
            f"/api/v1/automations/executions/{execution_id}/retry",
            headers=_headers(token),
        ).status_code
        == 409
    )
    assert (
        client_db.post(
            f"/api/v1/automations/executions/{execution_id}/retry",
            headers=_headers(other_token),
        ).status_code
        == 404
    )
    member_execution = asyncio.run(_seed(workspace_id, status="FAILED", terminal=True))

    async def make_member():
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == uuid.UUID(owner["user"]["id"]),
                )
            )
            membership.role = WorkspaceRole.MEMBER
            await session.commit()

    asyncio.run(make_member())
    assert (
        client_db.post(
            f"/api/v1/automations/executions/{member_execution}/retry",
            headers=_headers(token),
        ).status_code
        == 403
    )

    async def rerun():
        async with TestSessionLocal() as session:
            await AutomationService(session).run_executions(batch_size=1)
        async with TestSessionLocal() as session:
            row = await session.get(AutomationExecution, execution_id)
            assert row.effect_key == effect_key and row.status == "SUCCEEDED"
            assert len(row.failure_history) == 1
            assert await session.scalar(select(func.count(Notification.id))) == 1

    asyncio.run(rerun())


def test_success_cannot_retry_and_logs_exclude_payload(client_db, caplog):
    account, token = _account(client_db, "logging")
    workspace_id = uuid.UUID(account["workspace"]["id"])
    succeeded = asyncio.run(_seed(workspace_id, status="SUCCEEDED", attempt=1))
    response = client_db.post(
        f"/api/v1/automations/executions/{succeeded}/retry", headers=_headers(token)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AUTOMATION_EXECUTION_STATE_INVALID"
    marker = "never-log-sensitive-provider-payload"
    asyncio.run(
        _seed(workspace_id, action="unsupported.action", payload={"raw": marker})
    )

    async def run():
        async with TestSessionLocal() as session:
            await AutomationService(session).run_executions(batch_size=1)

    with caplog.at_level(logging.INFO, logger="app.services.automation"):
        asyncio.run(run())
    assert marker not in caplog.text
    assert "automation.execution.terminal_failure" in caplog.text


def test_manual_retry_and_stale_recovery_race_has_one_transition(client_db):
    account, _ = _account(client_db, "retry-race")
    workspace_id = uuid.UUID(account["workspace"]["id"])
    now = datetime.now(UTC)
    execution_id = asyncio.run(
        _seed(
            workspace_id,
            status="RUNNING",
            attempt=1,
            started=now - timedelta(minutes=2),
        )
    )

    async def recover():
        async with TestSessionLocal() as session:
            return await AutomationService(session).recover_stale_executions(
                stale_seconds=60, batch_size=1, now=now, worker_id="recovery"
            )

    async def retry():
        async with TestSessionLocal() as session:
            try:
                await AutomationService(session).retry_failed_execution(
                    workspace_id, execution_id, now=now
                )
            except Exception as exc:
                return getattr(exc, "code", None)
            return "RETRIED"

    async def scenario():
        recovered, retried = await asyncio.gather(recover(), retry())
        assert recovered == 1
        assert retried == "AUTOMATION_EXECUTION_STATE_INVALID"
        async with TestSessionLocal() as session:
            row = await session.get(AutomationExecution, execution_id)
            assert row.status == "PENDING"
            assert len(row.failure_history) == 1

    asyncio.run(scenario())
