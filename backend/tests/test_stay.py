"""PostgreSQL-backed physical Room and Stay lifecycle tests."""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.models.audit import WorkspaceAuditEvent
from app.models.booking import Booking, BookingStatus
from app.models.stay import (
    HotelRoom,
    RoomOperationalStatus,
    Stay,
    StayEvent,
    StayRoomAssignment,
    StayStatus,
)
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.stay import StayConflictError, StayOperationsService
from tests.conftest import TestSessionLocal
from tests.test_booking import _hold, _payload, _setup
from tests.test_hotel import _auth, _property, _room


def _physical_room(client, token, prop, room_type, code="101"):
    response = client.post(
        "/api/v1/hotel/rooms",
        headers=_auth(token),
        json={
            "property_id": prop["id"],
            "room_type_id": room_type["id"],
            "code": code,
            "floor": "1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _set_confirmed(*booking_ids):
    async def run():
        async with TestSessionLocal() as session:
            await session.execute(
                update(Booking)
                .where(Booking.id.in_([uuid.UUID(item) for item in booking_ids]))
                .values(status=BookingStatus.CONFIRMED)
            )
            await session.commit()

    asyncio.run(run())


def _booking(client, token, prop, room_type, plan, *, key="stay-1", **changes):
    response = _hold(client, token, _payload(prop, room_type, plan, key=key, **changes))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _stay(client, token, booking_id):
    return client.post(
        f"/api/v1/hotel/bookings/{booking_id}/stay", headers=_auth(token)
    )


def test_room_create_duplicate_code_and_bounded_order(client_db):
    _, token, prop, room_type, _ = _setup(client_db, email="stay-room@example.com")
    room_b = _physical_room(client_db, token, prop, room_type, "102")
    room_a = _physical_room(client_db, token, prop, room_type, "101")
    duplicate = client_db.post(
        "/api/v1/hotel/rooms",
        headers=_auth(token),
        json={
            "property_id": prop["id"],
            "room_type_id": room_type["id"],
            "code": "101",
        },
    )
    assert duplicate.status_code == 409
    response = client_db.get(
        "/api/v1/hotel/rooms?page=1&page_size=1", headers=_auth(token)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["items"][0]["id"] == room_a["id"]
    assert data["items"][0]["operational_status"] == "AVAILABLE"
    assert room_b["id"] != room_a["id"]


def test_room_operational_filters_are_workspace_scoped_and_composable(client_db):
    _, token, prop, room_type, _ = _setup(
        client_db, email="stay-room-filters@example.com"
    )
    room = _physical_room(client_db, token, prop, room_type)
    assert (
        client_db.post(
            f"/api/v1/hotel/housekeeping/rooms/{room['id']}/readiness-override",
            headers=_auth(token),
            json={
                "readiness_status": "DIRTY",
                "reason": "Inspection requires another housekeeping pass",
            },
        ).status_code
        == 200
    )
    result = client_db.get(
        "/api/v1/hotel/rooms",
        headers=_auth(token),
        params={
            "property_id": prop["id"],
            "room_type_id": room_type["id"],
            "operational_status": "AVAILABLE",
            "readiness_status": "DIRTY",
            "active": "true",
            "page": 1,
            "page_size": 1,
        },
    )
    assert result.status_code == 200
    data = result.json()["data"]
    assert data["total"] == data["total_pages"] == 1
    assert data["items"][0]["id"] == room["id"]


def test_room_workspace_and_catalog_scope(client_db):
    _, first_token, prop, room_type, _ = _setup(
        client_db, email="stay-scope-a@example.com"
    )
    _, second_token, _, _, _ = _setup(client_db, email="stay-scope-b@example.com")
    assert (
        client_db.post(
            "/api/v1/hotel/rooms",
            headers=_auth(second_token),
            json={
                "property_id": prop["id"],
                "room_type_id": room_type["id"],
                "code": "X",
            },
        ).status_code
        == 404
    )
    room = _physical_room(client_db, first_token, prop, room_type)
    assert (
        client_db.get(
            f"/api/v1/hotel/rooms/{room['id']}", headers=_auth(second_token)
        ).status_code
        == 404
    )


def test_only_confirmed_booking_creates_one_idempotent_stay(client_db):
    _, token, prop, room_type, plan = _setup(client_db, email="stay-create@example.com")
    booking = _booking(client_db, token, prop, room_type, plan)
    rejected = _stay(client_db, token, booking["id"])
    assert rejected.status_code == 409
    _set_confirmed(booking["id"])
    first = _stay(client_db, token, booking["id"])
    second = _stay(client_db, token, booking["id"])
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert first.json()["data"]["status"] == "EXPECTED"
    assert first.json()["data"]["required_room_count"] == 1
    assert [event["event_type"] for event in second.json()["data"]["events"]] == [
        "STAY_CREATED"
    ]


def test_multi_room_assignment_matches_booking_quantity(client_db):
    _, token, prop, room_type, plan = _setup(
        client_db, email="stay-multi@example.com", units=2
    )
    booking = _booking(client_db, token, prop, room_type, plan, quantity=2, key="multi")
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    rooms = [
        _physical_room(client_db, token, prop, room_type, code)
        for code in ("201", "202")
    ]
    incomplete = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/assign-room",
        headers=_auth(token),
        json={"room_ids": [rooms[0]["id"]]},
    )
    assert incomplete.status_code == 422
    assigned = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/assign-room",
        headers=_auth(token),
        json={"room_ids": [item["id"] for item in rooms]},
    )
    assert assigned.status_code == 200, assigned.text
    assert [item["code"] for item in assigned.json()["data"]["rooms"]] == [
        "201",
        "202",
    ]


def test_incompatible_cross_property_inactive_and_out_of_service_rooms_rejected(
    client_db,
):
    _, token, prop, room_type, plan = _setup(
        client_db, email="stay-room-rules@example.com", units=2
    )
    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    other_type = _room(client_db, token, prop["id"], code="SUITE")
    incompatible = _physical_room(client_db, token, prop, other_type, "301")
    response = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/assign-room",
        headers=_auth(token),
        json={"room_ids": [incompatible["id"]]},
    )
    assert response.status_code == 422
    other_property = _property(client_db, token, name="Other Hotel")
    other_property_type = _room(
        client_db, token, other_property["id"], code="DELUXE-OTHER"
    )
    cross_property = _physical_room(
        client_db, token, other_property, other_property_type, "OTHER-301"
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/assign-room",
            headers=_auth(token),
            json={"room_ids": [cross_property["id"]]},
        ).status_code
        == 422
    )
    inactive = _physical_room(client_db, token, prop, room_type, "302")
    assert (
        client_db.patch(
            f"/api/v1/hotel/rooms/{inactive['id']}",
            headers=_auth(token),
            json={"active": False},
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/assign-room",
            headers=_auth(token),
            json={"room_ids": [inactive["id"]]},
        ).status_code
        == 409
    )
    out = _physical_room(client_db, token, prop, room_type, "303")
    assert (
        client_db.post(
            f"/api/v1/hotel/rooms/{out['id']}/out-of-service",
            headers=_auth(token),
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/assign-room",
            headers=_auth(token),
            json={"room_ids": [out["id"]]},
        ).status_code
        == 409
    )


def test_check_in_and_check_out_are_transactional_and_idempotent(client_db):
    _, token, prop, room_type, plan = _setup(
        client_db, email="stay-lifecycle@example.com"
    )
    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)
    checked_in = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-in",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    assert checked_in.status_code == 200, checked_in.text
    data = checked_in.json()["data"]
    assert data["status"] == "CHECKED_IN"
    assert data["actual_check_in_at"] is not None
    assert data["rooms"][0]["operational_status"] == "OCCUPIED"
    assert (
        client_db.post(
            f"/api/v1/hotel/rooms/{room['id']}/out-of-service",
            headers=_auth(token),
        ).status_code
        == 409
    )
    first = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-out", headers=_auth(token)
    )
    second = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-out", headers=_auth(token)
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["status"] == "CHECKED_OUT"
    assert first.json()["data"]["actual_check_out_at"] is not None
    assert first.json()["data"]["rooms"][0]["operational_status"] == "AVAILABLE"
    assert [event["event_type"] for event in second.json()["data"]["events"]].count(
        "CHECKED_OUT"
    ) == 1

    async def audit_actions():
        async with TestSessionLocal() as session:
            return list(
                await session.scalars(
                    select(WorkspaceAuditEvent.action).where(
                        WorkspaceAuditEvent.resource_id == uuid.UUID(stay["id"])
                    )
                )
            )

    actions = asyncio.run(audit_actions())
    assert actions.count("CHECKED_IN") == 1
    assert actions.count("CHECKED_OUT") == 1


def test_no_show_releases_assignment_without_changing_booking(client_db):
    _, token, prop, room_type, plan = _setup(client_db, email="stay-noshow@example.com")
    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)
    client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/assign-room",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    first = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/no-show", headers=_auth(token)
    )
    second = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/no-show", headers=_auth(token)
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["status"] == "NO_SHOW"
    assert first.json()["data"]["rooms"][0]["released_at"] is not None
    booking_read = client_db.get(
        f"/api/v1/hotel/bookings/{booking['id']}", headers=_auth(token)
    )
    assert booking_read.json()["data"]["status"] == "CONFIRMED"
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-in",
            headers=_auth(token),
            json={"room_ids": [room["id"]]},
        ).status_code
        == 409
    )


def test_checked_in_stay_cannot_be_no_show(client_db):
    _, token, prop, room_type, plan = _setup(
        client_db, email="stay-invalid-state@example.com"
    )
    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)
    client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-in",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/no-show", headers=_auth(token)
        ).status_code
        == 409
    )


def test_concurrent_check_in_same_room_has_exactly_one_winner(client_db):
    user, token, prop, room_type, plan = _setup(
        client_db, email="stay-race@example.com", units=2
    )
    bookings = [
        _booking(client_db, token, prop, room_type, plan, key=f"race-{index}")
        for index in range(2)
    ]
    _set_confirmed(*(booking["id"] for booking in bookings))
    stays = [
        _stay(client_db, token, booking["id"]).json()["data"] for booking in bookings
    ]
    room = _physical_room(client_db, token, prop, room_type)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    actor_id = uuid.UUID(user["user"]["id"])

    async def contend(stay_id):
        async with TestSessionLocal() as session:
            try:
                await StayOperationsService(session).check_in(
                    workspace_id,
                    uuid.UUID(stay_id),
                    actor_id,
                    [uuid.UUID(room["id"])],
                )
                return True
            except StayConflictError:
                await session.rollback()
                return False

    async def run_race():
        return await asyncio.gather(*(contend(stay["id"]) for stay in stays))

    winners = asyncio.run(run_race())
    assert winners.count(True) == 1

    async def state():
        async with TestSessionLocal() as session:
            statuses = list(
                (
                    await session.scalars(
                        select(Stay.status).where(Stay.workspace_id == workspace_id)
                    )
                ).all()
            )
            active = await session.scalar(
                select(func.count(StayRoomAssignment.id)).where(
                    StayRoomAssignment.released_at.is_(None)
                )
            )
            saved_room = await session.get(HotelRoom, uuid.UUID(room["id"]))
            return statuses, active, saved_room.operational_status

    statuses, active, room_status = asyncio.run(state())
    assert statuses.count(StayStatus.CHECKED_IN) == 1
    assert statuses.count(StayStatus.EXPECTED) == 1
    assert active == 1
    assert room_status == RoomOperationalStatus.OCCUPIED


def test_customer_360_includes_stay_and_authoritative_timeline(client_db):
    _, token, prop, room_type, plan = _setup(client_db, email="stay-crm@example.com")
    customer = client_db.post(
        "/api/v1/customers",
        headers=_auth(token),
        json={"display_name": "Stay Guest", "email": "stay-guest@example.com"},
    ).json()["data"]
    booking = _booking(
        client_db,
        token,
        prop,
        room_type,
        plan,
        customer_id=customer["id"],
    )
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)
    client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-in",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    detail = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}", headers=_auth(token)
    )
    assert detail.status_code == 200, detail.text
    stay_summary = detail.json()["data"]["stays"][0]
    assert stay_summary["id"] == stay["id"]
    assert stay_summary["room_codes"] == ["101"]
    timeline = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}/timeline?page_size=50",
        headers=_auth(token),
    ).json()["data"]
    assert {item["type"] for item in timeline["items"]} >= {
        "STAY_CREATED",
        "ROOM_ASSIGNED",
        "CHECKED_IN",
    }


def test_member_reads_but_cannot_mutate_stays_or_rooms(client_db):
    user, token, prop, room_type, plan = _setup(
        client_db, email="stay-member@example.com"
    )
    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)

    async def demote():
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == uuid.UUID(user["workspace"]["id"])
                )
            )
            membership.role = WorkspaceRole.MEMBER
            for capability in ("room.read", "stay.read"):
                session.add(
                    WorkspaceMemberCapability(
                        workspace_id=membership.workspace_id,
                        membership_id=membership.id,
                        capability=capability,
                        granted_by_user_id=membership.user_id,
                        granted_at=datetime.now(UTC),
                    )
                )
            await session.commit()

    asyncio.run(demote())
    assert client_db.get("/api/v1/hotel/rooms", headers=_auth(token)).status_code == 200
    assert client_db.get("/api/v1/hotel/stays", headers=_auth(token)).status_code == 200
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-in",
            headers=_auth(token),
            json={"room_ids": [room["id"]]},
        ).status_code
        == 403
    )


def test_cross_workspace_stay_is_hidden(client_db):
    _, first_token, prop, room_type, plan = _setup(
        client_db, email="stay-hidden-a@example.com"
    )
    booking = _booking(client_db, first_token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, first_token, booking["id"]).json()["data"]
    _, second_token, _, _, _ = _setup(client_db, email="stay-hidden-b@example.com")
    assert (
        client_db.get(
            f"/api/v1/hotel/stays/{stay['id']}", headers=_auth(second_token)
        ).status_code
        == 404
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/no-show",
            headers=_auth(second_token),
        ).status_code
        == 404
    )


def test_stay_operational_filters_and_pagination_are_deterministic(client_db):
    _, token, prop, room_type, plan = _setup(
        client_db, units=2, email="stay-list-filters@example.com"
    )
    expected_booking = _booking(
        client_db, token, prop, room_type, plan, key="stay-filter-expected"
    )
    in_house_booking = _booking(
        client_db, token, prop, room_type, plan, key="stay-filter-in-house"
    )
    _set_confirmed(expected_booking["id"], in_house_booking["id"])
    expected = _stay(client_db, token, expected_booking["id"]).json()["data"]
    in_house = _stay(client_db, token, in_house_booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{in_house['id']}/check-in",
            headers=_auth(token),
            json={"room_ids": [room["id"]]},
        ).status_code
        == 200
    )

    expected_page = client_db.get(
        "/api/v1/hotel/stays",
        headers=_auth(token),
        params={
            "property_id": prop["id"],
            "status": "EXPECTED",
            "arrival_date": "2030-01-01",
            "page": 1,
            "page_size": 1,
        },
    ).json()["data"]
    in_house_page = client_db.get(
        "/api/v1/hotel/stays",
        headers=_auth(token),
        params={
            "property_id": prop["id"],
            "status": "CHECKED_IN",
            "departure_date": "2030-01-04",
            "page": 1,
            "page_size": 1,
        },
    ).json()["data"]
    assert expected_page["total"] == expected_page["total_pages"] == 1
    assert expected_page["items"][0]["id"] == expected["id"]
    assert in_house_page["total"] == in_house_page["total_pages"] == 1
    assert in_house_page["items"][0]["id"] == in_house["id"]


def test_stay_events_are_immutable_safe_and_deterministically_ordered(client_db):
    _, token, prop, room_type, plan = _setup(client_db, email="stay-events@example.com")
    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)
    result = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-in",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    ).json()["data"]
    assert [event["event_type"] for event in result["events"]] == [
        "STAY_CREATED",
        "ROOM_ASSIGNED",
        "CHECKED_IN",
    ]
    assert all("customer" not in event["event_metadata"] for event in result["events"])

    async def count_events():
        async with TestSessionLocal() as session:
            return await session.scalar(select(func.count(StayEvent.id)))

    assert asyncio.run(count_events()) == 3
