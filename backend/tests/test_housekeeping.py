"""PostgreSQL-backed housekeeping and room-readiness regressions."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.models.audit import WorkspaceAuditEvent
from app.models.housekeeping import (
    HousekeepingEvent,
    HousekeepingPriority,
    HousekeepingTask,
    HousekeepingTaskStatus,
    RoomReadinessOverrideEvent,
)
from app.models.stay import HotelRoom, RoomReadinessStatus
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.housekeeping import HousekeepingService
from tests.conftest import TestSessionLocal
from tests.test_booking import _setup
from tests.test_hotel import _auth
from tests.test_stay import _booking, _physical_room, _set_confirmed, _stay


def _checked_out(client, *, email="housekeeping@example.com"):
    user, token, prop, room_type, plan = _setup(client, units=2, email=email)
    booking = _booking(client, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client, token, booking["id"]).json()["data"]
    room = _physical_room(client, token, prop, room_type)
    checked_in = client.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-in",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    assert checked_in.status_code == 200, checked_in.text
    checked_out = client.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-out", headers=_auth(token)
    )
    assert checked_out.status_code == 200, checked_out.text
    tasks = client.get("/api/v1/hotel/housekeeping/tasks", headers=_auth(token)).json()[
        "data"
    ]["items"]
    return user, token, prop, room_type, plan, stay, room, tasks[0]


def test_checkout_marks_dirty_creates_one_task_and_retry_is_idempotent(client_db):
    _, token, _, _, _, stay, room, task = _checked_out(client_db)
    assert task["room_id"] == room["id"]
    assert task["status"] == "PENDING"
    assert task["readiness_status"] == "DIRTY"
    repeated = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-out", headers=_auth(token)
    )
    assert repeated.status_code == 200
    tasks = client_db.get(
        "/api/v1/hotel/housekeeping/tasks", headers=_auth(token)
    ).json()["data"]
    assert tasks["total"] == 1


def test_dirty_and_cleaning_rooms_cannot_be_assigned_or_checked_in(client_db):
    _, token, prop, room_type, plan, _, room, task = _checked_out(
        client_db, email="housekeeping-readiness@example.com"
    )
    booking = _booking(client_db, token, prop, room_type, plan, key="second")
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    assign = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/assign-room",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    assert assign.status_code == 409
    started = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
        headers=_auth(token),
    )
    assert started.status_code == 200
    assert started.json()["data"]["readiness_status"] == "CLEANING"
    check_in = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-in",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    assert check_in.status_code == 409


def test_start_complete_assignment_timestamps_events_and_ready_check_in(client_db):
    user, token, prop, room_type, plan, _, room, task = _checked_out(
        client_db, email="housekeeping-flow@example.com"
    )
    user_id = user["user"]["id"]
    assigned = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/assign",
        headers=_auth(token),
        json={"assigned_to_user_id": user_id},
    )
    assert assigned.status_code == 200
    first_start = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
        headers=_auth(token),
    )
    second_start = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
        headers=_auth(token),
    )
    assert first_start.status_code == second_start.status_code == 200
    first_complete = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/complete",
        headers=_auth(token),
    )
    second_complete = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/complete",
        headers=_auth(token),
    )
    assert first_complete.status_code == second_complete.status_code == 200
    data = second_complete.json()["data"]
    assert data["completed_at"] is not None
    assert data["readiness_status"] == "READY"
    assert [event["event_type"] for event in data["events"]] == [
        "ROOM_DIRTY",
        "HOUSEKEEPING_TASK_CREATED",
        "HOUSEKEEPING_ASSIGNED",
        "HOUSEKEEPING_STARTED",
        "HOUSEKEEPING_COMPLETED",
        "ROOM_READY",
    ]
    booking = _booking(client_db, token, prop, room_type, plan, key="ready")
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    result = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-in",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    assert result.status_code == 200, result.text


def test_cross_workspace_assignee_and_task_access_rejected(client_db):
    _, token, _, _, _, _, _, task = _checked_out(
        client_db, email="housekeeping-scope-a@example.com"
    )
    other, other_token, _, _, _ = _setup(
        client_db, email="housekeeping-scope-b@example.com"
    )
    response = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/assign",
        headers=_auth(token),
        json={"assigned_to_user_id": other["user"]["id"]},
    )
    assert response.status_code == 409
    assert (
        client_db.get(
            f"/api/v1/hotel/housekeeping/tasks/{task['id']}",
            headers=_auth(other_token),
        ).status_code
        == 404
    )


def test_out_of_service_preserves_readiness_and_task_state(client_db):
    _, token, _, _, _, _, room, task = _checked_out(
        client_db, email="housekeeping-oos@example.com"
    )
    out = client_db.post(
        f"/api/v1/hotel/rooms/{room['id']}/out-of-service", headers=_auth(token)
    )
    assert out.status_code == 200
    assert out.json()["data"]["readiness_status"] == "DIRTY"
    started = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
        headers=_auth(token),
    )
    assert started.status_code == 200
    completed = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/complete",
        headers=_auth(token),
    )
    assert completed.json()["data"]["operational_status"] == "OUT_OF_SERVICE"
    assert completed.json()["data"]["readiness_status"] == "READY"
    returned = client_db.post(
        f"/api/v1/hotel/rooms/{room['id']}/available", headers=_auth(token)
    )
    assert returned.json()["data"]["readiness_status"] == "READY"


def test_concurrent_completion_is_safe_and_events_not_duplicated(client_db):
    user, token, _, _, _, _, room, task = _checked_out(
        client_db, email="housekeeping-race@example.com"
    )
    client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
        headers=_auth(token),
    )
    workspace_id = uuid.UUID(user["workspace"]["id"])
    actor_id = uuid.UUID(user["user"]["id"])
    task_id = uuid.UUID(task["id"])

    async def complete():
        async with TestSessionLocal() as session:
            return await HousekeepingService(session).complete(
                workspace_id, task_id, actor_id
            )

    async def run():
        return await asyncio.gather(complete(), complete())

    results = asyncio.run(run())
    assert [result.status.value for result in results] == ["COMPLETED", "COMPLETED"]

    async def state():
        async with TestSessionLocal() as session:
            completed = await session.scalar(
                select(func.count(HousekeepingEvent.id)).where(
                    HousekeepingEvent.task_id == task_id,
                    HousekeepingEvent.event_type == "HOUSEKEEPING_COMPLETED",
                )
            )
            active = await session.scalar(
                select(func.count(HousekeepingTask.id)).where(
                    HousekeepingTask.room_id == uuid.UUID(room["id"]),
                    HousekeepingTask.status.in_(("PENDING", "IN_PROGRESS")),
                )
            )
            saved = await session.get(HotelRoom, uuid.UUID(room["id"]))
            return completed, active, saved.readiness_status

    completed, active, readiness = asyncio.run(state())
    assert completed == 1
    assert active == 0
    assert readiness == RoomReadinessStatus.READY


def test_member_can_work_assigned_task_but_cannot_manage_queue(client_db):
    user, token, _, _, _, _, _, task = _checked_out(
        client_db, email="housekeeping-member@example.com"
    )
    user_id = user["user"]["id"]
    workspace_id = uuid.UUID(user["workspace"]["id"])
    assigned = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/assign",
        headers=_auth(token),
        json={"assigned_to_user_id": user_id},
    )
    assert assigned.status_code == 200

    async def demote():
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == uuid.UUID(user_id),
                )
            )
            membership.role = WorkspaceRole.MEMBER
            for capability in ("housekeeping.read", "housekeeping.operate"):
                session.add(
                    WorkspaceMemberCapability(
                        workspace_id=workspace_id,
                        membership_id=membership.id,
                        capability=capability,
                        granted_by_user_id=membership.user_id,
                        granted_at=datetime.now(UTC),
                    )
                )
            await session.commit()

    asyncio.run(demote())
    assert (
        client_db.get(
            "/api/v1/hotel/housekeeping/tasks", headers=_auth(token)
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/housekeeping/tasks/{task['id']}/assign",
            headers=_auth(token),
            json={"assigned_to_user_id": user_id},
        ).status_code
        == 403
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/housekeeping/tasks/{task['id']}/cancel",
            headers=_auth(token),
        ).status_code
        == 403
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
            headers=_auth(token),
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/housekeeping/tasks/{task['id']}/complete",
            headers=_auth(token),
        ).status_code
        == 200
    )


def test_invalid_transitions_fail_closed_and_customer_data_is_not_exposed(client_db):
    _, token, _, _, _, _, _, task = _checked_out(
        client_db, email="housekeeping-transition@example.com"
    )
    complete = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/complete",
        headers=_auth(token),
    )
    assert complete.status_code == 409
    cancelled = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/cancel",
        headers=_auth(token),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["readiness_status"] == "DIRTY"
    assert (
        client_db.post(
            f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
            headers=_auth(token),
        ).status_code
        == 409
    )
    serialized = str(cancelled.json()["data"]).lower()
    assert "guest_name" not in serialized
    assert "guest_email" not in serialized
    assert "customer" not in serialized


def test_task_pagination_filters_and_order_are_deterministic(client_db):
    owner, token, prop, room_type, plan, _, _, first = _checked_out(
        client_db, email="housekeeping-page@example.com"
    )
    booking = _booking(client_db, token, prop, room_type, plan, key="page-second")
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type, code="102")
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-in",
            headers=_auth(token),
            json={"room_ids": [room["id"]]},
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-out", headers=_auth(token)
        ).status_code
        == 200
    )
    page_one = client_db.get(
        "/api/v1/hotel/housekeeping/tasks?page=1&page_size=1&status=PENDING",
        headers=_auth(token),
    ).json()["data"]
    page_two = client_db.get(
        "/api/v1/hotel/housekeeping/tasks?page=2&page_size=1&status=PENDING",
        headers=_auth(token),
    ).json()["data"]
    assert page_one["total"] == page_two["total"] == 2
    assert page_one["total_pages"] == page_two["total_pages"] == 2
    assert page_one["items"][0]["id"] == first["id"]
    assert page_two["items"][0]["room_id"] == room["id"]
    assigned = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{first['id']}/assign",
        headers=_auth(token),
        json={"assigned_to_user_id": owner["user"]["id"]},
    )
    assert assigned.status_code == 200
    filtered = client_db.get(
        "/api/v1/hotel/housekeeping/tasks",
        headers=_auth(token),
        params={
            "property_id": prop["id"],
            "status": "PENDING",
            "priority": "NORMAL",
            "readiness_status": "DIRTY",
            "assignee_id": owner["user"]["id"],
            "page": 1,
            "page_size": 1,
        },
    ).json()["data"]
    assert filtered["total"] == filtered["total_pages"] == 1
    assert filtered["items"][0]["id"] == first["id"]


def test_database_rejects_conflicting_active_task(client_db):
    user, _, prop, _, _, _, room, _ = _checked_out(
        client_db, email="housekeeping-active-constraint@example.com"
    )

    async def insert_conflict():
        async with TestSessionLocal() as session:
            session.add(
                HousekeepingTask(
                    workspace_id=uuid.UUID(user["workspace"]["id"]),
                    property_id=uuid.UUID(prop["id"]),
                    room_id=uuid.UUID(room["id"]),
                    stay_id=None,
                    priority=HousekeepingPriority.NORMAL,
                    created_by_user_id=uuid.UUID(user["user"]["id"]),
                    source="MANUAL",
                )
            )
            with pytest.raises(IntegrityError, match="uq_housekeeping_active_room"):
                await session.commit()

    asyncio.run(insert_conflict())


def test_database_rejects_cross_workspace_room_reference(client_db):
    _, first_token, prop, room_type, _ = _setup(
        client_db, email="housekeeping-room-scope-a@example.com"
    )
    room = _physical_room(client_db, first_token, prop, room_type)
    second, _, _, _, _ = _setup(
        client_db, email="housekeeping-room-scope-b@example.com"
    )

    async def insert_cross_workspace():
        async with TestSessionLocal() as session:
            session.add(
                HousekeepingTask(
                    workspace_id=uuid.UUID(second["workspace"]["id"]),
                    property_id=uuid.UUID(prop["id"]),
                    room_id=uuid.UUID(room["id"]),
                    stay_id=None,
                    priority=HousekeepingPriority.NORMAL,
                    created_by_user_id=uuid.UUID(second["user"]["id"]),
                    source="MANUAL",
                )
            )
            with pytest.raises(IntegrityError, match="fk_housekeeping_task_room_scope"):
                await session.commit()

    asyncio.run(insert_cross_workspace())


def test_unassigned_member_lacks_permission_to_operate_task(client_db):
    user, token, _, _, _, _, _, task = _checked_out(
        client_db, email="housekeeping-unassigned-member@example.com"
    )

    async def demote():
        async with TestSessionLocal() as session:
            await session.execute(
                update(WorkspaceMember)
                .where(
                    WorkspaceMember.workspace_id == uuid.UUID(user["workspace"]["id"]),
                    WorkspaceMember.user_id == uuid.UUID(user["user"]["id"]),
                )
                .values(role=WorkspaceRole.MEMBER)
            )
            await session.commit()

    asyncio.run(demote())
    response = client_db.post(
        f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
        headers=_auth(token),
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", [WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
def test_privileged_readiness_override_is_audited_and_resolves_active_task(
    client_db, role
):
    user, token, _, _, _, _, room, task = _checked_out(
        client_db, email=f"housekeeping-override-{role.value}@example.com"
    )

    if role == WorkspaceRole.ADMIN:

        async def make_admin():
            async with TestSessionLocal() as session:
                await session.execute(
                    update(WorkspaceMember)
                    .where(
                        WorkspaceMember.workspace_id
                        == uuid.UUID(user["workspace"]["id"]),
                        WorkspaceMember.user_id == uuid.UUID(user["user"]["id"]),
                    )
                    .values(role=WorkspaceRole.ADMIN)
                )
                await session.commit()

        asyncio.run(make_admin())

    reason = "Physical cleaning completed during system outage"
    response = client_db.post(
        f"/api/v1/hotel/housekeeping/rooms/{room['id']}/readiness-override",
        headers=_auth(token),
        json={"readiness_status": "READY", "reason": reason},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["readiness_status"] == "READY"
    assert data["event"]["previous_readiness"] == "DIRTY"
    assert data["event"]["new_readiness"] == "READY"
    assert data["event"]["reason"] == reason
    assert data["event"]["actor_user_id"] == user["user"]["id"]
    assert data["event"]["created_at"]

    async def audit_state():
        async with TestSessionLocal() as session:
            saved_event = await session.scalar(
                select(RoomReadinessOverrideEvent).where(
                    RoomReadinessOverrideEvent.id == uuid.UUID(data["event"]["id"])
                )
            )
            saved_task = await session.get(HousekeepingTask, uuid.UUID(task["id"]))
            global_audit = await session.scalar(
                select(WorkspaceAuditEvent).where(
                    WorkspaceAuditEvent.workspace_id
                    == uuid.UUID(user["workspace"]["id"]),
                    WorkspaceAuditEvent.resource_id == uuid.UUID(room["id"]),
                    WorkspaceAuditEvent.action == "ROOM_READINESS_OVERRIDDEN",
                )
            )
            return saved_event, saved_task.status, global_audit

    event, task_status, global_audit = asyncio.run(audit_state())
    assert event.workspace_id == uuid.UUID(user["workspace"]["id"])
    assert event.room_id == uuid.UUID(room["id"])
    assert task_status == HousekeepingTaskStatus.CANCELLED
    assert global_audit.actor_user_id == uuid.UUID(user["user"]["id"])
    assert global_audit.safe_metadata == {
        "previous_readiness": "DIRTY",
        "new_readiness": "READY",
    }


def test_readiness_override_rejects_member_missing_reason_invalid_and_occupied(
    client_db,
):
    user, token, prop, room_type, plan = _setup(
        client_db, units=2, email="housekeeping-override-safety@example.com"
    )
    room = _physical_room(client_db, token, prop, room_type)
    url = f"/api/v1/hotel/housekeeping/rooms/{room['id']}/readiness-override"
    assert (
        client_db.post(
            url,
            headers=_auth(token),
            json={"readiness_status": "DIRTY", "reason": "short"},
        ).status_code
        == 422
    )
    assert (
        client_db.post(
            url,
            headers=_auth(token),
            json={
                "readiness_status": "CLEANING",
                "reason": "Attempt an invalid direct cleaning state",
            },
        ).status_code
        == 409
    )

    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-in",
            headers=_auth(token),
            json={"room_ids": [room["id"]]},
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            url,
            headers=_auth(token),
            json={
                "readiness_status": "DIRTY",
                "reason": "Attempt to alter an occupied room readiness",
            },
        ).status_code
        == 409
    )

    async def demote():
        async with TestSessionLocal() as session:
            await session.execute(
                update(WorkspaceMember)
                .where(
                    WorkspaceMember.workspace_id == uuid.UUID(user["workspace"]["id"])
                )
                .values(role=WorkspaceRole.MEMBER)
            )
            await session.commit()

    asyncio.run(demote())
    assert (
        client_db.post(
            url,
            headers=_auth(token),
            json={
                "readiness_status": "DIRTY",
                "reason": "Member attempts a privileged readiness correction",
            },
        ).status_code
        == 403
    )


def test_readiness_override_workspace_isolation_and_dirty_task_creation(client_db):
    owner, token, prop, room_type, _ = _setup(
        client_db, email="housekeeping-override-scope-a@example.com"
    )
    room = _physical_room(client_db, token, prop, room_type)
    _, other_token, _, _, _ = _setup(
        client_db, email="housekeeping-override-scope-b@example.com"
    )
    url = f"/api/v1/hotel/housekeeping/rooms/{room['id']}/readiness-override"
    payload = {
        "readiness_status": "DIRTY",
        "reason": "Manual inspection found the room requires cleaning",
    }
    assert (
        client_db.post(url, headers=_auth(other_token), json=payload).status_code == 404
    )
    response = client_db.post(url, headers=_auth(token), json=payload)
    assert response.status_code == 200
    tasks = client_db.get(
        "/api/v1/hotel/housekeeping/tasks?readiness_status=DIRTY",
        headers=_auth(token),
    ).json()["data"]
    assert tasks["total"] == 1
    assert tasks["items"][0]["room_id"] == room["id"]
    assert tasks["items"][0]["source"] == "READINESS_OVERRIDE"
    assert response.json()["data"]["event"]["workspace_id"] == owner["workspace"]["id"]
