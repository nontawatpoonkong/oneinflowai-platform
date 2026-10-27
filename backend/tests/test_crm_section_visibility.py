"""Customer360 gates every data section on its own capability.

guest.read covers the guest profile (contact details, identities, tags,
preferences, notes) only. Booking data needs booking.read, stay data needs
stay.read, conversation previews and content need conversation.read, and
payment data needs payment.read. Hidden sections are never queried, so they
cannot leak through bodies, metadata, summaries, counts, the timeline, list
fields, list filters, or errors. Reads and denials write nothing.
"""

import asyncio
import uuid

from sqlalchemy import func, select, update

from app.models.audit import WorkspaceAuditEvent
from app.models.booking import Booking
from app.models.conversation import Conversation
from app.models.conversation_read_state import ConversationReadState
from app.models.crm import CustomerCRMEvent
from app.models.customer import Customer
from app.models.stay import Stay
from app.models.workspace_member import WorkspaceRole
from tests.conftest import TestSessionLocal
from tests.test_booking import _hold, _payload, _setup
from tests.test_crm import _conversation, _customer
from tests.test_crm_payment_visibility import _payment_customer
from tests.test_hotel import _auth
from tests.test_stay import _set_confirmed, _stay
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

GUEST_EMAIL = "section.guest@example.com"
GUEST_NOTE = "Prefers a late check-out"
MESSAGE_TEXT = "Need a quiet room"
ROOM_TYPE_NAME = "Deluxe"
SECTIONS = ("bookings", "stays", "conversations")


def _guest_with_history(client, email):
    """Owner Workspace with a repeat guest holding bookings, a stay and a chat."""

    owner, token, prop, room, plan = _setup(client, email=email, units=2)
    customer = _customer(client, token, "Section Guest")
    bookings = []
    for key in ("section-1", "section-2"):
        held = _hold(
            client,
            token,
            _payload(prop, room, plan, key=key, customer_id=customer["id"]),
        )
        assert held.status_code == 201, held.text
        bookings.append(held.json()["data"]["id"])
    _set_confirmed(*bookings)
    stay = _stay(client, token, bookings[0])
    assert stay.status_code == 201, stay.text
    conversation_id = _conversation(client, token, customer["id"])

    async def mark_attention():
        async with TestSessionLocal() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .values(needs_attention=True)
            )
            await session.commit()

    asyncio.run(mark_attention())
    note = client.post(
        f"/api/v1/crm/customers/{customer['id']}/notes",
        headers=_auth(token),
        json={"body": GUEST_NOTE},
    )
    assert note.status_code == 201, note.text
    return {
        "owner": owner,
        "token": token,
        "workspace_id": owner["workspace"]["id"],
        "customer": customer,
        "bookings": bookings,
        "stay": stay.json()["data"]["id"],
        "conversation": conversation_id,
    }


def _member(client, world, email, capabilities):
    user, token = _zero_workspace_account(client, email)
    membership_id = _add_member(world["workspace_id"], user["id"], WorkspaceRole.MEMBER)
    _grant(client, world, membership_id, capabilities)
    return _headers(token, world["workspace_id"]), membership_id


def _grant(client, world, membership_id, capabilities):
    granted = client.put(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}/capabilities",
        headers=_headers(world["token"]),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text


def _state(world):
    """Rows a Customer360 read could plausibly touch, plus the audit count."""

    async def read():
        async with TestSessionLocal() as session:
            workspace_id = uuid.UUID(world["workspace_id"])
            customer = await session.get(Customer, uuid.UUID(world["customer"]["id"]))
            bookings = [
                (await session.get(Booking, uuid.UUID(item))).updated_at
                for item in world["bookings"]
            ]
            stay = await session.get(Stay, uuid.UUID(world["stay"]))
            conversation = await session.get(
                Conversation, uuid.UUID(world["conversation"])
            )

            async def count(model):
                return await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.workspace_id == workspace_id)
                )

            return (
                customer.updated_at,
                bookings,
                stay.updated_at,
                conversation.updated_at,
                await count(ConversationReadState),
                await count(CustomerCRMEvent),
                await count(WorkspaceAuditEvent),
            )

    return asyncio.run(read())


def _read_all(client, world, headers):
    customer_id = world["customer"]["id"]
    detail = client.get(f"/api/v1/crm/customers/{customer_id}", headers=headers)
    timeline = client.get(
        f"/api/v1/crm/customers/{customer_id}/timeline?page_size=50", headers=headers
    )
    listing = client.get("/api/v1/crm/customers", headers=headers)
    for response in (detail, timeline, listing):
        assert response.status_code == 200, response.text
    return detail, timeline, listing


def _assert_profile(detail, world):
    data = detail.json()["data"]
    assert data["customer"]["id"] == world["customer"]["id"]
    assert data["customer"]["email"] == GUEST_EMAIL
    assert [note["body"] for note in data["notes"]] == [GUEST_NOTE]


def _assert_bookings(detail, timeline, listing, world, *, visible):
    data = detail.json()["data"]
    timeline_data = timeline.json()["data"]
    item = listing.json()["data"]["items"][0]
    booking_events = [
        event for event in timeline_data["items"] if event["entity_type"] == "booking"
    ]
    if visible:
        assert data["bookings_visible"] is True
        assert sorted(item["id"] for item in data["bookings"]) == sorted(
            world["bookings"]
        )
        assert data["repeat_guest_summary"]["confirmed_bookings"] == 2
        assert data["repeat_guest_summary"]["repeat_guest"] is True
        assert booking_events
        assert timeline_data["bookings_visible"] is True
        assert listing.json()["data"]["bookings_visible"] is True
        assert item["booking_count"] == 2
        assert item["confirmed_bookings"] == 2
        assert item["repeat_guest"] is True
        assert item["latest_booking_status"] == "CONFIRMED"
        return
    assert data["bookings"] == []
    assert data["repeat_guest_summary"] is None
    assert booking_events == []
    for key in (
        "booking_count",
        "confirmed_bookings",
        "repeat_guest",
        "latest_booking_status",
    ):
        assert item[key] is None, key
    for response in (detail, timeline, listing):
        assert ROOM_TYPE_NAME not in response.text
        assert "HOLD_CREATED" not in response.text
        assert "CONFIRMED" not in response.text
    # Leak checks come first so they fail before the flags were introduced.
    assert data["bookings_visible"] is False
    assert timeline_data["bookings_visible"] is False
    assert listing.json()["data"]["bookings_visible"] is False


def _assert_stays(detail, timeline, world, *, visible):
    data = detail.json()["data"]
    timeline_data = timeline.json()["data"]
    stay_events = [
        event for event in timeline_data["items"] if event["entity_type"] == "stay"
    ]
    if visible:
        assert data["stays_visible"] is True
        assert [item["id"] for item in data["stays"]] == [world["stay"]]
        assert [event["entity_id"] for event in stay_events] == [world["stay"]]
        assert timeline_data["stays_visible"] is True
        return
    assert data["stays"] == []
    assert stay_events == []
    for response in (detail, timeline):
        assert world["stay"] not in response.text
        assert "STAY_CREATED" not in response.text
        assert "EXPECTED" not in response.text
    assert data["stays_visible"] is False
    assert timeline_data["stays_visible"] is False


def _assert_conversations(detail, timeline, listing, world, *, visible):
    data = detail.json()["data"]
    timeline_data = timeline.json()["data"]
    item = listing.json()["data"]["items"][0]
    conversation_events = [
        event
        for event in timeline_data["items"]
        if event["entity_type"] == "conversation"
    ]
    if visible:
        assert data["conversations_visible"] is True
        assert [item["id"] for item in data["conversations"]] == [world["conversation"]]
        assert data["conversations"][0]["preview"] == MESSAGE_TEXT
        assert conversation_events
        assert timeline_data["conversations_visible"] is True
        assert listing.json()["data"]["conversations_visible"] is True
        assert item["last_conversation_at"] is not None
        assert item["needs_attention"] is True
        return
    assert data["conversations"] == []
    assert conversation_events == []
    assert item["last_conversation_at"] is None
    assert item["needs_attention"] is None
    for response in (detail, timeline, listing):
        assert world["conversation"] not in response.text
        assert MESSAGE_TEXT not in response.text
        assert "CONVERSATION_STARTED" not in response.text
    assert data["conversations_visible"] is False
    assert timeline_data["conversations_visible"] is False
    assert listing.json()["data"]["conversations_visible"] is False


def _assert_sections(client, world, headers, *, bookings, stays, conversations):
    detail, timeline, listing = _read_all(client, world, headers)
    _assert_profile(detail, world)
    _assert_bookings(detail, timeline, listing, world, visible=bookings)
    _assert_stays(detail, timeline, world, visible=stays)
    _assert_conversations(detail, timeline, listing, world, visible=conversations)
    if not bookings and not stays:
        # A visible stay references its booking id; nothing else may.
        for response in (detail, timeline, listing):
            for booking_id in world["bookings"]:
                assert booking_id not in response.text
            assert "2030-01-01" not in response.text
    # The timeline total counts only events the caller may see.
    timeline_data = timeline.json()["data"]
    assert timeline_data["total"] == len(timeline_data["items"])
    return detail, timeline, listing


def test_guest_read_only_sees_profile_without_other_sections(client_db):
    world = _guest_with_history(client_db, "c360-guest-only@example.com")
    member, _ = _member(
        client_db, world, "c360-guest-reader@example.com", ["guest.read"]
    )
    before = _state(world)
    detail, timeline, listing = _assert_sections(
        client_db, world, member, bookings=False, stays=False, conversations=False
    )
    assert detail.json()["data"]["payments_visible"] is False
    # Only the profile note remains on the timeline.
    assert [item["type"] for item in timeline.json()["data"]["items"]] == ["NOTE_ADDED"]
    assert _state(world) == before


def test_booking_read_opens_booking_data_only(client_db):
    world = _guest_with_history(client_db, "c360-booking@example.com")
    member, _ = _member(
        client_db,
        world,
        "c360-booking-reader@example.com",
        ["guest.read", "booking.read"],
    )
    _assert_sections(
        client_db, world, member, bookings=True, stays=False, conversations=False
    )
    for query_name in ("has_active_booking", "repeat_guest"):
        response = client_db.get(
            f"/api/v1/crm/customers?{query_name}=true", headers=member
        )
        assert response.status_code == 200, response.text
        assert [
            item["customer"]["id"] for item in response.json()["data"]["items"]
        ] == [world["customer"]["id"]]


def test_stay_read_opens_stay_data_only(client_db):
    world = _guest_with_history(client_db, "c360-stay@example.com")
    member, _ = _member(
        client_db, world, "c360-stay-reader@example.com", ["guest.read", "stay.read"]
    )
    _assert_sections(
        client_db, world, member, bookings=False, stays=True, conversations=False
    )


def test_conversation_read_opens_conversation_data_only(client_db):
    world = _guest_with_history(client_db, "c360-chat@example.com")
    member, _ = _member(
        client_db,
        world,
        "c360-chat-reader@example.com",
        ["guest.read", "conversation.read"],
    )
    _assert_sections(
        client_db, world, member, bookings=False, stays=False, conversations=True
    )
    response = client_db.get(
        "/api/v1/crm/customers?needs_attention=true", headers=member
    )
    assert response.status_code == 200, response.text
    assert [item["customer"]["id"] for item in response.json()["data"]["items"]] == [
        world["customer"]["id"]
    ]


def test_payment_read_keeps_payment_data_without_booking_details(client_db):
    owner, owner_token, customer, payment_id = _payment_customer(
        client_db, "c360-payment-owner@example.com"
    )
    world = {"workspace_id": owner["workspace"]["id"], "token": owner_token}
    member, _ = _member(
        client_db,
        world,
        "c360-payment-reader@example.com",
        ["guest.read", "payment.read"],
    )
    detail = client_db.get(f"/api/v1/crm/customers/{customer['id']}", headers=member)
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["payments_visible"] is True
    assert [item["id"] for item in data["payments"]] == [payment_id]
    assert data["payment_exceptions"][0]["reason"] == "AMOUNT_MISMATCH"
    assert data["bookings"] == []
    assert data["repeat_guest_summary"] is None
    timeline = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}/timeline?page_size=50",
        headers=member,
    ).json()["data"]
    types = {item["entity_type"] for item in timeline["items"]}
    assert "payment" in types
    assert "booking" not in types
    assert not {"PAYMENT_LINKED", "HOLD_CREATED"} & {
        item["type"] for item in timeline["items"]
    }
    listed = client_db.get(
        "/api/v1/crm/customers?has_payment_exception=true", headers=member
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["items"][0]["has_payment_exception"] is True
    assert listed.json()["data"]["items"][0]["booking_count"] is None


def test_customer360_cross_workspace_ids_leak_no_section(client_db):
    world = _guest_with_history(client_db, "c360-tenant-a@example.com")
    _, other_token, *_ = _setup(client_db, email="c360-tenant-b@example.com")
    before = _state(world)
    other = _auth(other_token)
    customer_id = world["customer"]["id"]
    secrets = (
        GUEST_EMAIL,
        GUEST_NOTE,
        MESSAGE_TEXT,
        world["stay"],
        world["conversation"],
        *world["bookings"],
    )
    for path in (
        f"/api/v1/crm/customers/{customer_id}",
        f"/api/v1/crm/customers/{customer_id}/timeline",
    ):
        response = client_db.get(path, headers=other)
        assert response.status_code == 404, response.text
        for value in secrets:
            assert value not in response.text
    for query in ("", "?has_active_booking=true", "?needs_attention=true"):
        listing = client_db.get(f"/api/v1/crm/customers{query}", headers=other)
        assert listing.status_code == 200, listing.text
        assert listing.json()["data"]["items"] == []
    forged = client_db.get(
        f"/api/v1/crm/customers/{customer_id}",
        headers={**other, "X-Workspace-ID": world["workspace_id"]},
    )
    assert forged.status_code == 403, forged.text
    for value in secrets:
        assert value not in forged.text
    assert _state(world) == before


def test_restricted_filters_are_rejected_without_leaking(client_db):
    world = _guest_with_history(client_db, "c360-filters@example.com")
    member, _ = _member(
        client_db, world, "c360-filter-reader@example.com", ["guest.read"]
    )
    no_guest, _ = _member(
        client_db,
        world,
        "c360-no-guest@example.com",
        ["booking.read", "stay.read", "conversation.read", "payment.read"],
    )
    before = _state(world)
    for query_name, capability in (
        ("has_active_booking", "booking.read"),
        ("repeat_guest", "booking.read"),
        ("needs_attention", "conversation.read"),
        ("has_payment_exception", "payment.read"),
    ):
        for value in ("true", "false"):
            response = client_db.get(
                f"/api/v1/crm/customers?{query_name}={value}", headers=member
            )
            assert response.status_code == 403, response.text
            body = response.json()
            assert body["error"]["code"] == "FORBIDDEN"
            assert capability in body["message"]
            for secret in (GUEST_EMAIL, world["customer"]["id"], MESSAGE_TEXT):
                assert secret not in response.text
    # Section capabilities never stand in for guest.read.
    customer_id = world["customer"]["id"]
    for path in (
        "/api/v1/crm/customers",
        f"/api/v1/crm/customers/{customer_id}",
        f"/api/v1/crm/customers/{customer_id}/timeline",
    ):
        response = client_db.get(path, headers=no_guest)
        assert response.status_code == 403, response.text
        assert GUEST_EMAIL not in response.text
        assert world["conversation"] not in response.text
    assert _state(world) == before


def test_grant_changes_take_effect_on_next_request(client_db):
    world = _guest_with_history(client_db, "c360-grants@example.com")
    member, membership_id = _member(
        client_db, world, "c360-grant-reader@example.com", ["guest.read"]
    )
    _assert_sections(
        client_db, world, member, bookings=False, stays=False, conversations=False
    )
    _grant(client_db, world, membership_id, ["guest.read", "booking.read", "stay.read"])
    _assert_sections(
        client_db, world, member, bookings=True, stays=True, conversations=False
    )
    _grant(client_db, world, membership_id, ["guest.read", "conversation.read"])
    _assert_sections(
        client_db, world, member, bookings=False, stays=False, conversations=True
    )
    _grant(client_db, world, membership_id, [])
    response = client_db.get(
        f"/api/v1/crm/customers/{world['customer']['id']}", headers=member
    )
    assert response.status_code == 403, response.text
    assert GUEST_EMAIL not in response.text


def test_owner_and_fully_granted_member_see_every_section(client_db):
    world = _guest_with_history(client_db, "c360-full@example.com")
    member, _ = _member(
        client_db,
        world,
        "c360-full-reader@example.com",
        [
            "guest.read",
            "booking.read",
            "stay.read",
            "conversation.read",
            "payment.read",
        ],
    )
    before = _state(world)
    for headers in (_auth(world["token"]), member):
        detail, _, listing = _assert_sections(
            client_db, world, headers, bookings=True, stays=True, conversations=True
        )
        assert detail.json()["data"]["payments_visible"] is True
        assert listing.json()["data"]["items"][0]["has_payment_exception"] is False
    assert _state(world) == before
