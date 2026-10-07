"""PostgreSQL-backed Booking Hold lifecycle and inventory safety tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.channels import ChannelType
from app.models.booking import Booking, BookingEvent, BookingItem, BookingStatus
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.hotel import InventoryDate
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.booking import BookingHoldCreate
from app.services.booking import (
    BookingService,
    BookingTransitionError,
    BookingUnavailableError,
)
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_hotel import _auth, _inventory, _property, _rate, _room


def _setup(client, *, units=1, email="booking-owner@example.com", **changes):
    client.headers["host"] = "localhost"
    user, token = register_verify_and_login(client, email=email)
    prop = _property(client, token)
    room = _room(client, token, prop["id"])
    plan = _rate(client, token, prop["id"], room["id"])
    inventory = _inventory(
        client,
        token,
        prop["id"],
        room["id"],
        total_units=units,
        reserved_units=0,
        blocked_units=0,
        **changes,
    )
    assert inventory.status_code == 200, inventory.text
    return user, token, prop, room, plan


def _payload(prop, room, plan, *, key="hold-1", **changes):
    return {
        "property_id": prop["id"],
        "room_type_id": room["id"],
        "rate_plan_id": plan["id"],
        "check_in": "2030-01-01",
        "check_out": "2030-01-04",
        "adults": 2,
        "children": 0,
        "quantity": 1,
        "guest_name": "ABC Guest",
        "idempotency_key": key,
        **changes,
    }


def _hold(client, token, payload):
    return client.post(
        "/api/v1/hotel/bookings/hold", headers=_auth(token), json=payload
    )


def _inventory_rows(workspace_id):
    async def read():
        async with TestSessionLocal() as session:
            result = await session.execute(
                select(InventoryDate)
                .where(InventoryDate.workspace_id == workspace_id)
                .order_by(InventoryDate.inventory_date)
            )
            return [
                (row.inventory_date.isoformat(), row.reserved_units)
                for row in result.scalars()
            ]

    return asyncio.run(read())


def test_hold_snapshots_three_nights_and_reserves_each_day(client_db):
    user, token, prop, room, plan = _setup(client_db)
    response = _hold(client_db, token, _payload(prop, room, plan))
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "HELD"
    assert data["subtotal"] == data["total_amount"] == "4500.75"
    assert data["currency"] == "THB"
    assert data["property_name_snapshot"] == "ABC Hotel"
    assert data["item"]["room_type_name_snapshot"] == "Deluxe"
    assert data["item"]["rate_plan_name_snapshot"] == "Flexible"
    assert [rate["amount"] for rate in data["item"]["nightly_rates"]] == ["1500.25"] * 3
    assert [event["event_type"] for event in data["events"]] == [
        "BOOKING_CREATED",
        "HOLD_CREATED",
    ]
    assert _inventory_rows(uuid.UUID(user["workspace"]["id"])) == [
        ("2030-01-01", 1),
        ("2030-01-02", 1),
        ("2030-01-03", 1),
    ]


def test_price_and_policy_snapshot_survive_rate_change(client_db):
    _, token, prop, room, plan = _setup(client_db)
    booking = _hold(client_db, token, _payload(prop, room, plan)).json()["data"]
    changed = client_db.patch(
        f"/api/v1/hotel/rate-plans/{plan['id']}",
        headers=_auth(token),
        json={"base_price": "9999.99", "refundable": False},
    )
    assert changed.status_code == 200
    read = client_db.get(
        f"/api/v1/hotel/bookings/{booking['id']}", headers=_auth(token)
    )
    assert read.status_code == 200
    item = read.json()["data"]["item"]
    assert read.json()["data"]["total_amount"] == "4500.75"
    assert item["rate_policy_snapshot"]["base_price"] == "1500.25"
    assert item["rate_policy_snapshot"]["refundable"] is True


def test_idempotent_retry_and_conflicting_payload(client_db):
    user, token, prop, room, plan = _setup(client_db, units=2)
    payload = _payload(prop, room, plan)
    first = _hold(client_db, token, payload)
    second = _hold(client_db, token, payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    conflict = _hold(client_db, token, {**payload, "quantity": 2})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "BOOKING_CONFLICT"
    assert {
        count for _, count in _inventory_rows(uuid.UUID(user["workspace"]["id"]))
    } == {1}
    assert (
        len(
            client_db.get("/api/v1/hotel/bookings", headers=_auth(token)).json()["data"]
        )
        == 1
    )


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"adults": 3}, 422),
        ({"children": 2}, 422),
        ({"check_out": "2030-01-01"}, 422),
        ({"quantity": 0}, 422),
    ],
)
def test_invalid_booking_inputs_do_not_reserve(client_db, change, expected):
    user, token, prop, room, plan = _setup(client_db)
    response = _hold(client_db, token, _payload(prop, room, plan, **change))
    assert response.status_code == expected
    assert {
        count for _, count in _inventory_rows(uuid.UUID(user["workspace"]["id"]))
    } == {0}


@pytest.mark.parametrize("kind", ["property", "room", "rate"])
def test_inactive_catalog_rejects_hold(client_db, kind):
    user, token, prop, room, plan = _setup(client_db)
    target = {
        "property": ("properties", prop),
        "room": ("room-types", room),
        "rate": ("rate-plans", plan),
    }[kind]
    updated = client_db.patch(
        f"/api/v1/hotel/{target[0]}/{target[1]['id']}",
        headers=_auth(token),
        json={"active": False},
    )
    assert updated.status_code == 200
    assert _hold(client_db, token, _payload(prop, room, plan)).status_code == 409
    assert {
        count for _, count in _inventory_rows(uuid.UUID(user["workspace"]["id"]))
    } == {0}


def test_missing_or_sold_out_night_rejects_whole_stay(client_db):
    user, token, prop, room, plan = _setup(client_db, end_date="2030-01-02")
    assert _hold(client_db, token, _payload(prop, room, plan)).status_code == 409
    assert {
        count for _, count in _inventory_rows(uuid.UUID(user["workspace"]["id"]))
    } == {0}
    assert (
        _inventory(
            client_db,
            token,
            prop["id"],
            room["id"],
            start_date="2030-01-03",
            end_date="2030-01-03",
            total_units=0,
            reserved_units=0,
            blocked_units=0,
        ).status_code
        == 200
    )
    assert _hold(client_db, token, _payload(prop, room, plan)).status_code == 409


def test_advance_cancel_and_repeated_cancel_release_once(client_db):
    user, token, prop, room, plan = _setup(client_db)
    booking = _hold(client_db, token, _payload(prop, room, plan)).json()["data"]
    url = f"/api/v1/hotel/bookings/{booking['id']}"
    advanced = client_db.post(f"{url}/advance-to-payment", headers=_auth(token))
    assert advanced.status_code == 200
    assert advanced.json()["data"]["status"] == "PENDING_PAYMENT"
    assert (
        _hold(client_db, token, _payload(prop, room, plan, key="other")).status_code
        == 409
    )
    first = client_db.post(f"{url}/cancel", headers=_auth(token))
    second = client_db.post(f"{url}/cancel", headers=_auth(token))
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["status"] == "CANCELLED"
    assert (
        len(first.json()["data"]["events"]) == len(second.json()["data"]["events"]) == 4
    )
    assert {
        count for _, count in _inventory_rows(uuid.UUID(user["workspace"]["id"]))
    } == {0}
    assert (
        client_db.post(f"{url}/advance-to-payment", headers=_auth(token)).status_code
        == 409
    )


def test_expiry_releases_inventory_exactly_once(client_db):
    user, token, prop, room, plan = _setup(client_db)
    booking = _hold(client_db, token, _payload(prop, room, plan)).json()["data"]
    workspace_id = uuid.UUID(user["workspace"]["id"])

    async def expire():
        async with TestSessionLocal() as session:
            service = BookingService(session)
            before = await service.get(workspace_id, uuid.UUID(booking["id"]))
            assert before.status == BookingStatus.HELD
            first = await service.expire(
                workspace_id, before.id, now=datetime.now(UTC) + timedelta(minutes=16)
            )
            second = await service.expire(
                workspace_id, before.id, now=datetime.now(UTC) + timedelta(minutes=16)
            )
            assert first.status == second.status == BookingStatus.EXPIRED

    asyncio.run(expire())
    assert {count for _, count in _inventory_rows(workspace_id)} == {0}
    read = client_db.get(
        f"/api/v1/hotel/bookings/{booking['id']}", headers=_auth(token)
    ).json()["data"]
    assert [e["event_type"] for e in read["events"]].count("HOLD_EXPIRED") == 1


def test_inventory_admin_cannot_overwrite_active_hold(client_db):
    user, token, prop, room, plan = _setup(client_db)
    _hold(client_db, token, _payload(prop, room, plan))
    response = _inventory(
        client_db,
        token,
        prop["id"],
        room["id"],
        total_units=5,
        reserved_units=0,
        blocked_units=0,
    )
    assert response.status_code == 409
    assert {
        count for _, count in _inventory_rows(uuid.UUID(user["workspace"]["id"]))
    } == {1}


def test_cross_workspace_catalog_and_customer_rejected(client_db):
    first, first_token, prop, room, plan = _setup(
        client_db, email="booking-a@example.com"
    )
    second, second_token = register_verify_and_login(
        client_db, email="booking-b@example.com"
    )
    foreign = _hold(client_db, second_token, _payload(prop, room, plan))
    assert foreign.status_code == 404
    first_ws = uuid.UUID(first["workspace"]["id"])
    second_ws = uuid.UUID(second["workspace"]["id"])
    customer_id = uuid.uuid4()

    async def seed():
        async with TestSessionLocal() as session:
            session.add(
                Customer(id=customer_id, workspace_id=second_ws, display_name="Other")
            )
            await session.commit()

    asyncio.run(seed())
    response = _hold(
        client_db, first_token, _payload(prop, room, plan, customer_id=str(customer_id))
    )
    assert response.status_code == 404
    assert {count for _, count in _inventory_rows(first_ws)} == {0}


def test_member_cannot_manage_bookings_and_no_confirm_endpoint(client_db):
    user, token, prop, room, plan = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])

    async def demote():
        async with TestSessionLocal() as session:
            await session.execute(
                update(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .values(role=WorkspaceRole.MEMBER)
            )
            await session.commit()

    asyncio.run(demote())
    assert _hold(client_db, token, _payload(prop, room, plan)).status_code == 403
    assert (
        client_db.get("/api/v1/hotel/bookings", headers=_auth(token)).status_code == 403
    )
    assert (
        client_db.patch(
            f"/api/v1/hotel/bookings/{uuid.uuid4()}",
            headers=_auth(token),
            json={"status": "CONFIRMED"},
        ).status_code
        == 405
    )


def test_concurrent_last_unit_has_one_winner(client_db):
    user, _, prop, room, plan = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    actor = uuid.UUID(user["user"]["id"])

    async def contend(key):
        async with TestSessionLocal() as session:
            request = BookingHoldCreate.model_validate(
                _payload(prop, room, plan, key=key)
            )
            try:
                booking = await BookingService(session).create_hold(
                    workspace_id, actor, request
                )
                return booking.id
            except BookingUnavailableError:
                return None

    async def run_race():
        return await asyncio.gather(contend("race-a"), contend("race-b"))

    winners = asyncio.run(run_race())
    assert sum(value is not None for value in winners) == 1
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}

    async def counts():
        async with TestSessionLocal() as session:
            bookings = list(
                (
                    await session.execute(
                        select(Booking).where(Booking.workspace_id == workspace_id)
                    )
                ).scalars()
            )
            items = list((await session.execute(select(BookingItem))).scalars())
            events = list((await session.execute(select(BookingEvent))).scalars())
            return len(bookings), len(items), len(events)

    assert asyncio.run(counts()) == (1, 1, 2)


def test_quantity_and_precise_decimal_totals(client_db):
    user, token, prop, room, plan = _setup(client_db, units=2)
    response = _hold(client_db, token, _payload(prop, room, plan, quantity=2))
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["total_amount"] == "9001.50"
    assert data["item"]["quantity"] == 2
    assert {
        count for _, count in _inventory_rows(uuid.UUID(user["workspace"]["id"]))
    } == {2}


def test_expire_due_batch_and_premature_expiry(client_db):
    user, token, prop, room, plan = _setup(client_db)
    booking = _hold(client_db, token, _payload(prop, room, plan)).json()["data"]
    workspace_id = uuid.UUID(user["workspace"]["id"])

    async def run():
        async with TestSessionLocal() as session:
            service = BookingService(session)
            with pytest.raises(BookingTransitionError) as premature:
                await service.expire(workspace_id, uuid.UUID(booking["id"]))
            assert (
                getattr(premature.value, "code", None) == "BOOKING_TRANSITION_INVALID"
            )
            await session.execute(
                update(Booking)
                .where(Booking.id == uuid.UUID(booking["id"]))
                .values(hold_expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
            assert await service.expire_due_holds(workspace_id) == 1
            assert await service.expire_due_holds(workspace_id) == 0

    asyncio.run(run())
    assert {count for _, count in _inventory_rows(workspace_id)} == {0}


def test_conversation_scope_and_customer_consistency(client_db):
    first, token, prop, room, plan = _setup(
        client_db, email="booking-conv-a@example.com"
    )
    second, _ = register_verify_and_login(client_db, email="booking-conv-b@example.com")
    first_ws = uuid.UUID(first["workspace"]["id"])
    second_ws = uuid.UUID(second["workspace"]["id"])
    own_customer, other_customer, own_conversation, other_conversation = [
        uuid.uuid4() for _ in range(4)
    ]

    async def seed():
        async with TestSessionLocal() as session:
            session.add_all(
                [
                    Customer(
                        id=own_customer, workspace_id=first_ws, display_name="Own"
                    ),
                    Customer(
                        id=other_customer, workspace_id=second_ws, display_name="Other"
                    ),
                    Conversation(
                        id=own_conversation,
                        workspace_id=first_ws,
                        customer_id=own_customer,
                        channel=ChannelType.WEB,
                    ),
                    Conversation(
                        id=other_conversation,
                        workspace_id=second_ws,
                        customer_id=other_customer,
                        channel=ChannelType.WEB,
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed())
    foreign = _hold(
        client_db,
        token,
        _payload(prop, room, plan, conversation_id=str(other_conversation)),
    )
    assert foreign.status_code == 404
    mismatch = _hold(
        client_db,
        token,
        _payload(
            prop,
            room,
            plan,
            conversation_id=str(own_conversation),
            customer_id=str(other_customer),
        ),
    )
    assert mismatch.status_code == 404
    linked = _hold(
        client_db,
        token,
        _payload(prop, room, plan, conversation_id=str(own_conversation)),
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["data"]["customer_id"] == str(own_customer)
    assert linked.json()["data"]["conversation_id"] == str(own_conversation)


def test_concurrent_same_key_returns_same_booking_and_single_reservation(client_db):
    user, _, prop, room, plan = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    actor = uuid.UUID(user["user"]["id"])
    request = BookingHoldCreate.model_validate(_payload(prop, room, plan))

    async def contend():
        async with TestSessionLocal() as session:
            return (
                await BookingService(session).create_hold(workspace_id, actor, request)
            ).id

    async def run():
        return await asyncio.gather(contend(), contend())

    ids = asyncio.run(run())
    assert ids[0] == ids[1]
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}


def test_failed_commit_rolls_back_booking_and_every_inventory_day(
    client_db, monkeypatch
):
    user, _, prop, room, plan = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    actor = uuid.UUID(user["user"]["id"])

    async def run():
        async with TestSessionLocal() as session:

            async def fail_after_flush():
                await session.flush()
                raise RuntimeError("injected test failure")

            monkeypatch.setattr(session, "commit", fail_after_flush)
            request = BookingHoldCreate.model_validate(_payload(prop, room, plan))
            with pytest.raises(RuntimeError, match="injected test failure"):
                await BookingService(session).create_hold(workspace_id, actor, request)
            return await session.scalar(select(Booking.id))

    assert asyncio.run(run()) is None
    assert {count for _, count in _inventory_rows(workspace_id)} == {0}


def test_draft_to_hold_reprices_and_reserves_only_when_activated(client_db):
    user, token, prop, room, plan = _setup(client_db)
    payload = _payload(prop, room, plan, key="draft-to-hold")
    draft = client_db.post(
        "/api/v1/hotel/bookings/draft", headers=_auth(token), json=payload
    )
    assert draft.status_code == 201, draft.text
    booking = draft.json()["data"]
    assert booking["status"] == "DRAFT"
    assert booking["hold_expires_at"] is None
    assert len(booking["events"]) == 1
    workspace_id = uuid.UUID(user["workspace"]["id"])
    assert {count for _, count in _inventory_rows(workspace_id)} == {0}
    updated = client_db.patch(
        f"/api/v1/hotel/rate-plans/{plan['id']}",
        headers=_auth(token),
        json={"base_price": "1700.00"},
    )
    assert updated.status_code == 200
    held = client_db.post(
        f"/api/v1/hotel/bookings/{booking['id']}/hold", headers=_auth(token)
    )
    assert held.status_code == 200, held.text
    assert held.json()["data"]["status"] == "HELD"
    assert held.json()["data"]["total_amount"] == "5100.00"
    assert (
        held.json()["data"]["item"]["rate_policy_snapshot"]["base_price"] == "1700.00"
    )
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}
    assert (
        client_db.post(
            f"/api/v1/hotel/bookings/{booking['id']}/hold", headers=_auth(token)
        ).status_code
        == 409
    )
    retry = client_db.post(
        "/api/v1/hotel/bookings/draft", headers=_auth(token), json=payload
    )
    assert retry.status_code == 201
    assert retry.json()["data"]["id"] == booking["id"]
    assert len(retry.json()["data"]["events"]) == 2


def test_draft_to_cancel_does_not_release_unreserved_inventory(client_db):
    user, token, prop, room, plan = _setup(client_db)
    payload = _payload(prop, room, plan, key="draft-cancel")
    draft = client_db.post(
        "/api/v1/hotel/bookings/draft", headers=_auth(token), json=payload
    ).json()["data"]
    url = f"/api/v1/hotel/bookings/{draft['id']}/cancel"
    first = client_db.post(url, headers=_auth(token))
    second = client_db.post(url, headers=_auth(token))
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["status"] == "CANCELLED"
    assert (
        len(first.json()["data"]["events"]) == len(second.json()["data"]["events"]) == 2
    )
    assert {
        count for _, count in _inventory_rows(uuid.UUID(user["workspace"]["id"]))
    } == {0}
    assert (
        client_db.post(
            f"/api/v1/hotel/bookings/{draft['id']}/hold", headers=_auth(token)
        ).status_code
        == 409
    )
