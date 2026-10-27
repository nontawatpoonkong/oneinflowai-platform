"""Sprint 10.0 authoritative Hotel catalog and availability regressions."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.integrations.hotel_availability import SearchAvailabilityTool
from app.models.hotel import InventoryDate
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.hotel import AvailabilitySearchRequest
from tests.conftest import TestSessionLocal, register_verify_and_login


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _owner(client, email="hotel-owner@example.com"):
    client.headers["host"] = "localhost"
    data, token = register_verify_and_login(client, email=email)
    return data["workspace"]["id"], token


def _property(client, token, **overrides):
    payload = {
        "name": "ABC Hotel",
        "timezone": "Asia/Bangkok",
        "currency": "THB",
        "check_in_time": "14:00:00",
        "check_out_time": "12:00:00",
        **overrides,
    }
    response = client.post(
        "/api/v1/hotel/properties", headers=_auth(token), json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _room(client, token, property_id, **overrides):
    payload = {
        "property_id": property_id,
        "code": "DELUXE",
        "name": "Deluxe",
        "max_adults": 2,
        "max_children": 1,
        "max_occupancy": 3,
        "base_capacity": 2,
        **overrides,
    }
    response = client.post(
        "/api/v1/hotel/room-types", headers=_auth(token), json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _rate(client, token, property_id, room_type_id, **overrides):
    payload = {
        "property_id": property_id,
        "room_type_id": room_type_id,
        "code": "FLEX",
        "name": "Flexible",
        "currency": "THB",
        "base_price": "1500.25",
        "refundable": True,
        "cancellation_policy_summary": "Cancel one day before arrival",
        **overrides,
    }
    response = client.post(
        "/api/v1/hotel/rate-plans", headers=_auth(token), json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _inventory(client, token, property_id, room_type_id, **overrides):
    payload = {
        "property_id": property_id,
        "room_type_id": room_type_id,
        "start_date": "2030-01-01",
        "end_date": "2030-01-03",
        "total_units": 5,
        "reserved_units": 1,
        "blocked_units": 1,
        **overrides,
    }
    return client.put("/api/v1/hotel/inventory", headers=_auth(token), json=payload)


def _search(client, token, property_id, **overrides):
    payload = {
        "property_id": property_id,
        "check_in": "2030-01-01",
        "check_out": "2030-01-04",
        "adults": 2,
        "children": 1,
        **overrides,
    }
    return client.post(
        "/api/v1/hotel/availability/search", headers=_auth(token), json=payload
    )


def test_hotel_catalog_inventory_and_deterministic_multi_night_quote(client_db):
    _, token = _owner(client_db)
    property_value = _property(client_db, token)
    room = _room(client_db, token, property_value["id"])
    rate = _rate(client_db, token, property_value["id"], room["id"])
    inventory = _inventory(client_db, token, property_value["id"], room["id"])
    assert inventory.status_code == 200
    assert len(inventory.json()["data"]) == 3
    assert {item["available_units"] for item in inventory.json()["data"]} == {3}

    response = _search(client_db, token, property_value["id"])
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["nights"] == 3
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["room_type_id"] == room["id"]
    assert result["rate_plan_id"] == rate["id"]
    assert result["available_units"] == 3
    assert result["subtotal"] == "4500.75"
    assert [night["amount"] for night in result["nightly_rates"]] == [
        "1500.25",
        "1500.25",
        "1500.25",
    ]

    quote = client_db.post(
        "/api/v1/hotel/quotes",
        headers=_auth(token),
        json={
            "property_id": property_value["id"],
            "check_in": "2030-01-01",
            "check_out": "2030-01-04",
            "adults": 2,
            "children": 0,
            "rate_plan_id": rate["id"],
        },
    )
    assert quote.status_code == 200
    assert quote.json()["data"]["results"][0]["subtotal"] == "4500.75"


def test_minimum_availability_and_sold_out_day_control_whole_stay(client_db):
    _, token = _owner(client_db)
    prop = _property(client_db, token)
    room = _room(client_db, token, prop["id"])
    _rate(client_db, token, prop["id"], room["id"])
    assert _inventory(client_db, token, prop["id"], room["id"]).status_code == 200
    assert (
        _inventory(
            client_db,
            token,
            prop["id"],
            room["id"],
            start_date="2030-01-02",
            end_date="2030-01-02",
            total_units=5,
            reserved_units=3,
            blocked_units=1,
        ).status_code
        == 200
    )
    assert (
        _search(client_db, token, prop["id"]).json()["data"]["results"][0][
            "available_units"
        ]
        == 1
    )

    assert (
        _inventory(
            client_db,
            token,
            prop["id"],
            room["id"],
            start_date="2030-01-03",
            end_date="2030-01-03",
            total_units=5,
            reserved_units=4,
            blocked_units=1,
        ).status_code
        == 200
    )
    assert _search(client_db, token, prop["id"]).json()["data"]["results"] == []


def test_missing_inventory_and_inactive_catalog_are_excluded(client_db):
    _, token = _owner(client_db)
    prop = _property(client_db, token)
    room = _room(client_db, token, prop["id"])
    rate = _rate(client_db, token, prop["id"], room["id"])
    assert _search(client_db, token, prop["id"]).json()["data"]["results"] == []
    assert _inventory(client_db, token, prop["id"], room["id"]).status_code == 200

    for path in (
        f"/api/v1/hotel/rate-plans/{rate['id']}",
        f"/api/v1/hotel/room-types/{room['id']}",
        f"/api/v1/hotel/properties/{prop['id']}",
    ):
        changed = client_db.patch(path, headers=_auth(token), json={"active": False})
        assert changed.status_code == 200
        assert _search(client_db, token, prop["id"]).json()["data"]["results"] == []
        client_db.patch(path, headers=_auth(token), json={"active": True})


@pytest.mark.parametrize(
    "payload_change",
    [
        {"max_adults": 0},
        {"max_children": -1},
        {"max_adults": 3, "max_occupancy": 2},
        {"base_capacity": 4, "max_occupancy": 3},
    ],
)
def test_invalid_occupancy_is_rejected(client_db, payload_change):
    _, token = _owner(
        client_db, email=f"occupancy-{abs(hash(str(payload_change)))}@example.com"
    )
    prop = _property(client_db, token)
    payload = {
        "property_id": prop["id"],
        "code": "BAD",
        "name": "Bad",
        "max_adults": 2,
        "max_children": 1,
        "max_occupancy": 3,
        "base_capacity": 2,
        **payload_change,
    }
    response = client_db.post(
        "/api/v1/hotel/room-types", headers=_auth(token), json=payload
    )
    assert response.status_code == 422


def test_invalid_dates_inventory_invariant_and_occupancy_are_rejected(client_db):
    _, token = _owner(client_db)
    prop = _property(client_db, token)
    room = _room(client_db, token, prop["id"])
    _rate(client_db, token, prop["id"], room["id"])
    assert (
        _inventory(
            client_db,
            token,
            prop["id"],
            room["id"],
            start_date="2030-01-03",
            end_date="2030-01-01",
        ).status_code
        == 422
    )
    assert (
        _inventory(
            client_db,
            token,
            prop["id"],
            room["id"],
            total_units=2,
            reserved_units=2,
            blocked_units=1,
        ).status_code
        == 422
    )
    assert (
        _search(client_db, token, prop["id"], check_out="2030-01-01").status_code == 422
    )
    assert _inventory(client_db, token, prop["id"], room["id"]).status_code == 200
    assert (
        _search(client_db, token, prop["id"], adults=3).json()["data"]["results"] == []
    )
    assert (
        _search(client_db, token, prop["id"], adults=2, children=2).json()["data"][
            "results"
        ]
        == []
    )


def test_workspace_isolation_and_cross_workspace_parents_are_rejected(client_db):
    _, first = _owner(client_db, "first-hotel@example.com")
    prop = _property(client_db, first)
    room = _room(client_db, first, prop["id"])
    _, second = _owner(client_db, "second-hotel@example.com")

    assert (
        client_db.get(
            f"/api/v1/hotel/properties/{prop['id']}", headers=_auth(second)
        ).status_code
        == 404
    )
    cross_room = client_db.post(
        "/api/v1/hotel/room-types",
        headers=_auth(second),
        json={
            "property_id": prop["id"],
            "code": "CROSS",
            "name": "Cross",
            "max_adults": 2,
            "max_children": 0,
            "max_occupancy": 2,
            "base_capacity": 2,
        },
    )
    assert cross_room.status_code == 404
    cross_rate = client_db.post(
        "/api/v1/hotel/rate-plans",
        headers=_auth(second),
        json={
            "property_id": prop["id"],
            "room_type_id": room["id"],
            "code": "CROSS",
            "name": "Cross",
            "currency": "THB",
            "base_price": "1.00",
        },
    )
    assert cross_rate.status_code == 404
    assert _search(client_db, second, prop["id"]).status_code == 404


def test_search_availability_tool_is_typed_read_only_and_does_not_mutate_inventory(
    client_db,
):
    workspace_id, token = _owner(client_db)
    prop = _property(client_db, token)
    room = _room(client_db, token, prop["id"])
    _rate(client_db, token, prop["id"], room["id"])
    _inventory(client_db, token, prop["id"], room["id"])

    async def run():
        async with TestSessionLocal() as session:
            before = list(
                (
                    await session.execute(
                        select(
                            InventoryDate.id,
                            InventoryDate.total_units,
                            InventoryDate.reserved_units,
                            InventoryDate.blocked_units,
                        ).where(InventoryDate.workspace_id == workspace_id)
                    )
                ).all()
            )
            tool = SearchAvailabilityTool(session)
            result = await tool.execute(
                workspace_id,
                AvailabilitySearchRequest(
                    property_id=prop["id"],
                    check_in=date(2030, 1, 1),
                    check_out=date(2030, 1, 4),
                    adults=2,
                    children=0,
                ),
            )
            after = list(
                (
                    await session.execute(
                        select(
                            InventoryDate.id,
                            InventoryDate.total_units,
                            InventoryDate.reserved_units,
                            InventoryDate.blocked_units,
                        ).where(InventoryDate.workspace_id == workspace_id)
                    )
                ).all()
            )
            assert tool.name == "search_availability"
            assert tool.read_only is True
            assert result.results[0].subtotal == Decimal("4500.75")
            assert before == after

    asyncio.run(run())


def test_member_can_read_but_cannot_manage_hotel_catalog(client_db):
    workspace_id, token = _owner(client_db)
    prop = _property(client_db, token)

    async def demote():
        async with TestSessionLocal() as session:
            await session.execute(
                update(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .values(role=WorkspaceRole.MEMBER)
            )
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id
                )
            )
            session.add(
                WorkspaceMemberCapability(
                    workspace_id=workspace_id,
                    membership_id=membership.id,
                    capability="room.read",
                    granted_by_user_id=membership.user_id,
                    granted_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(demote())
    assert (
        client_db.get("/api/v1/hotel/properties", headers=_auth(token)).status_code
        == 200
    )
    denied = client_db.patch(
        f"/api/v1/hotel/properties/{prop['id']}",
        headers=_auth(token),
        json={"name": "Forbidden"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
