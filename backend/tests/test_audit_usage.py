"""Global audit and non-invasive first-party usage regression coverage."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.audit import (
    AuditActorType,
    AuditArea,
    ProductUsageEvent,
    WorkspaceAuditEvent,
)
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.audit import AuditService, safe_audit_metadata
from app.services.workspace_capability import WorkspaceCapability
from tests.conftest import TestSessionLocal, register_verify_and_login


def _account(client, email):
    data, token = register_verify_and_login(client, email=email)
    return data, {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": data["workspace"]["id"],
    }


async def _set_member_access(workspace_id, role, capabilities=()):
    async with TestSessionLocal() as session:
        member = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == uuid.UUID(workspace_id)
            )
        )
        member.role = role
        session.add_all(
            WorkspaceMemberCapability(
                workspace_id=member.workspace_id,
                membership_id=member.id,
                capability=value,
                granted_by_user_id=member.user_id,
                granted_at=datetime.now(UTC),
            )
            for value in capabilities
        )
        await session.commit()


def _event_payload(path="/dashboard", *, navigation_id=None, properties=None):
    return {
        "event_name": "PAGE_VIEW",
        "navigation_id": str(navigation_id or uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "page_path": path,
        "feature": "HOME" if path == "/dashboard" else "ANALYTICS",
        "safe_properties": properties or {},
        "occurred_at": datetime.now(UTC).isoformat(),
    }


def test_audit_is_append_only_and_sensitive_metadata_fails_closed(client_db):
    data, _ = _account(client_db, "audit-immutable@example.com")
    workspace_id = uuid.UUID(data["workspace"]["id"])

    async def exercise():
        async with TestSessionLocal() as session:
            event = AuditService(session).record(
                workspace_id=workspace_id,
                actor_user_id=uuid.UUID(data["user"]["id"]),
                actor_type=AuditActorType.USER,
                action="WORKSPACE_SETTINGS_UPDATED",
                area=AuditArea.WORKSPACE,
                resource_type="Workspace",
                resource_id=workspace_id,
                metadata={"changed_fields": ["name"]},
            )
            await session.commit()
            event.action = "TAMPERED"
            with pytest.raises(RuntimeError, match="append-only"):
                await session.commit()

    asyncio.run(exercise())
    with pytest.raises(ValueError, match="Sensitive"):
        safe_audit_metadata({"api_token": "must-not-be-stored"})
    with pytest.raises(ValueError, match="Sensitive"):
        safe_audit_metadata({"changes": [{"authorization_header": "secret"}]})


def test_workspace_provisioning_emits_minimal_global_audit(client_db):
    data, headers = _account(client_db, "audit-provision@example.com")
    response = client_db.get("/api/v1/audit/events", headers=headers)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    actions = {item["action"] for item in items}
    assert {"WORKSPACE_CREATED", "WORKSPACE_PROVISIONED"} <= actions
    assert all(
        item["safe_metadata"] == {}
        for item in items
        if item["action"] == "WORKSPACE_CREATED"
    )
    assert data["workspace"]["id"] not in str([item["safe_metadata"] for item in items])


def test_audit_authorization_filtering_and_workspace_isolation(client_db):
    first, first_headers = _account(client_db, "audit-first@example.com")
    second, second_headers = _account(client_db, "audit-second@example.com")
    filtered = client_db.get(
        "/api/v1/audit/events",
        headers=first_headers,
        params={"area": "WORKSPACE", "action": "WORKSPACE_CREATED", "page_size": 1},
    )
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] == 1
    assert second["workspace"]["id"] not in filtered.text

    asyncio.run(_set_member_access(first["workspace"]["id"], WorkspaceRole.MEMBER))
    assert (
        client_db.get("/api/v1/audit/events", headers=first_headers).status_code == 403
    )
    asyncio.run(
        _set_member_access(
            first["workspace"]["id"],
            WorkspaceRole.MEMBER,
            [WorkspaceCapability.AUDIT_READ.value],
        )
    )
    assert (
        client_db.get("/api/v1/audit/events", headers=first_headers).status_code == 200
    )
    assert (
        client_db.get("/api/v1/audit/events", headers=second_headers).status_code == 200
    )


def test_audit_order_is_deterministic_and_detail_is_scoped(client_db):
    first, headers = _account(client_db, "audit-order@example.com")
    _, other_headers = _account(client_db, "audit-order-other@example.com")
    response = client_db.get("/api/v1/audit/events", headers=headers)
    items = response.json()["data"]["items"]
    ordering = [(item["occurred_at"], item["id"]) for item in items]
    assert ordering == sorted(ordering, reverse=True)
    event_id = items[0]["id"]
    assert (
        client_db.get(f"/api/v1/audit/events/{event_id}", headers=headers).status_code
        == 200
    )
    assert (
        client_db.get(
            f"/api/v1/audit/events/{event_id}", headers=other_headers
        ).status_code
        == 404
    )
    assert first["workspace"]["id"] not in str(items[0]["safe_metadata"])


def test_audit_query_filters_and_pagination_are_bounded(client_db):
    data, headers = _account(client_db, "audit-filters@example.com")
    now = datetime.now(UTC)
    page = client_db.get(
        "/api/v1/audit/events",
        headers=headers,
        params={
            "page": 1,
            "page_size": 1,
            "actor_user_id": data["user"]["id"],
            "action": "WORKSPACE_CREATED",
            "area": "WORKSPACE",
            "result": "SUCCESS",
            "start_at": (now - timedelta(minutes=5)).isoformat(),
            "end_at": (now + timedelta(minutes=5)).isoformat(),
        },
    )
    assert page.status_code == 200
    assert page.json()["data"]["total"] == 1
    assert len(page.json()["data"]["items"]) == 1
    assert page.json()["data"]["items"][0]["actor"]["id"] == data["user"]["id"]
    assert (
        client_db.get(
            "/api/v1/audit/events",
            headers=headers,
            params={"start_at": now.isoformat(), "end_at": now.isoformat()},
        ).status_code
        == 422
    )
    assert (
        client_db.get(
            "/api/v1/audit/events",
            headers=headers,
            params={
                "start_at": "2026-01-01T00:00:00",
                "end_at": "2026-01-02T00:00:00",
            },
        ).status_code
        == 422
    )


def test_usage_identity_is_trusted_and_navigation_is_idempotent(client_db):
    first, headers = _account(client_db, "usage-trusted@example.com")
    second, _ = _account(client_db, "usage-other@example.com")
    navigation_id = uuid.uuid4()
    payload = _event_payload(navigation_id=navigation_id)
    for _ in range(2):
        response = client_db.post(
            "/api/v1/analytics/events", headers=headers, json=payload
        )
        assert response.status_code == 201

    async def inspect():
        async with TestSessionLocal() as session:
            rows = list(await session.scalars(select(ProductUsageEvent)))
            matching = [item for item in rows if item.navigation_id == navigation_id]
            assert len(matching) == 1
            assert str(matching[0].workspace_id) == first["workspace"]["id"]
            assert str(matching[0].user_id) == first["user"]["id"]
            assert str(matching[0].workspace_id) != second["workspace"]["id"]

    asyncio.run(inspect())


def test_legitimate_repeat_home_views_and_home_analytics(client_db):
    _, headers = _account(client_db, "usage-repeat@example.com")
    for _ in range(2):
        assert (
            client_db.post(
                "/api/v1/analytics/events", headers=headers, json=_event_payload()
            ).status_code
            == 201
        )
    now = datetime.now(UTC)
    result = client_db.get(
        "/api/v1/analytics/overview",
        headers=headers,
        params={
            "start": (now - timedelta(days=1)).isoformat(),
            "end": (now + timedelta(minutes=1)).isoformat(),
        },
    ).json()["data"]["usage"]
    assert result["home_views"] == 2
    assert result["home_unique_users"] == 1
    assert result["recent_home_viewers"][0]["views"] == 2
    assert sum(point["count"] for point in result["home_views_by_day"]) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {**_event_payload(), "event_name": "KEYSTROKE"},
        _event_payload(path="/outside"),
        _event_payload(properties={"password": "not allowed"}),
        {**_event_payload(), "page_path": "/dashboard?customer_message=secret"},
        {**_event_payload(), "session_id": "not-a-uuid"},
        {**_event_payload(), "occurred_at": "2026-01-01T00:00:00"},
        _event_payload(properties={"label": "x" * 1000}),
    ],
)
def test_usage_rejects_invalid_or_sensitive_payload(client_db, payload):
    _, headers = _account(client_db, f"usage-invalid-{uuid.uuid4()}@example.com")
    assert (
        client_db.post(
            "/api/v1/analytics/events", headers=headers, json=payload
        ).status_code
        == 422
    )


def test_usage_is_workspace_scoped_in_analytics(client_db):
    _, first_headers = _account(client_db, "usage-scope-first@example.com")
    _, second_headers = _account(client_db, "usage-scope-second@example.com")
    client_db.post(
        "/api/v1/analytics/events", headers=first_headers, json=_event_payload()
    )
    now = datetime.now(UTC)
    params = {
        "start": (now - timedelta(days=1)).isoformat(),
        "end": (now + timedelta(minutes=1)).isoformat(),
    }
    first = client_db.get(
        "/api/v1/analytics/overview", headers=first_headers, params=params
    ).json()["data"]["usage"]
    second = client_db.get(
        "/api/v1/analytics/overview", headers=second_headers, params=params
    ).json()["data"]["usage"]
    assert first["home_views"] == 1
    assert second["home_views"] == 0


def test_usage_model_contains_no_content_capture_fields(client_db):
    _account(client_db, "usage-columns@example.com")
    columns = set(ProductUsageEvent.__table__.columns.keys())
    assert not columns & {
        "keystrokes",
        "form_contents",
        "customer_message",
        "clipboard",
        "mouse_coordinates",
        "dom_snapshot",
        "screen_recording",
    }
    assert {"page_path", "feature", "session_id", "navigation_id"} <= columns


def test_global_audit_model_is_distinct_from_usage_model(client_db):
    _account(client_db, "audit-distinct@example.com")
    assert WorkspaceAuditEvent.__tablename__ != ProductUsageEvent.__tablename__
    assert "action" in WorkspaceAuditEvent.__table__.columns
    assert "page_path" not in WorkspaceAuditEvent.__table__.columns
    assert "page_path" in ProductUsageEvent.__table__.columns
    assert asyncio.run(_usage_count()) == 0


async def _usage_count():
    async with TestSessionLocal() as session:
        return int(
            await session.scalar(select(func.count()).select_from(ProductUsageEvent))
            or 0
        )
