"""PostgreSQL-backed Guest CRM and Customer 360 tests."""

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.core.channels import ChannelType
from app.models.booking import Booking, BookingStatus
from app.models.conversation import Conversation
from app.models.crm import CustomerCRMEvent, CustomerPreference
from app.models.customer_identity import CustomerIdentity
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_booking import _hold, _payload, _setup
from tests.test_booking_payment_confirmation import (
    _advance,
    _confirm,
    _link,
    _mark_verified,
    _prepared,
)
from tests.test_hotel import _auth


def _customer(client, token, name="ABC Guest"):
    response = client.post(
        "/api/v1/customers",
        headers=_auth(token),
        json={
            "display_name": name,
            "full_name": name,
            "email": f"{name.lower().replace(' ', '.')}@example.com",
            "phone": "+66812345678",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _conversation(client, token, customer_id):
    response = client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={"customer_id": customer_id, "channel": "line"},
    )
    assert response.status_code == 201, response.text
    conversation_id = response.json()["data"]["id"]
    message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_auth(token),
        json={"sender_type": "customer", "content": "Need a quiet room"},
    )
    assert message.status_code == 201, message.text
    return conversation_id


def _add_identity(workspace_id, customer_id):
    async def run():
        async with TestSessionLocal() as session:
            session.add(
                CustomerIdentity(
                    workspace_id=uuid.UUID(workspace_id),
                    customer_id=uuid.UUID(customer_id),
                    channel=ChannelType.LINE,
                    external_user_id=f"line-{customer_id}",
                    external_username="abc-guest",
                )
            )
            await session.commit()

    asyncio.run(run())


def test_customer_360_includes_profile_identity_and_conversation_summary(client_db):
    user, token = register_verify_and_login(client_db, email="crm-profile@example.com")
    customer = _customer(client_db, token)
    conversation_id = _conversation(client_db, token, customer["id"])
    _add_identity(user["workspace"]["id"], customer["id"])

    response = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["customer"]["id"] == customer["id"]
    assert data["identities"][0]["channel"] == "line"
    assert "external_user_id" not in data["identities"][0]
    assert data["conversations"][0]["id"] == conversation_id
    assert data["conversations"][0]["preview"] == "Need a quiet room"
    assert data["conversations"][0]["unread"] is True


def test_preference_create_update_source_and_ai_source_rejection(client_db):
    _, token = register_verify_and_login(client_db, email="crm-pref@example.com")
    customer = _customer(client_db, token)
    url = f"/api/v1/crm/customers/{customer['id']}/preferences"
    created = client_db.post(
        url,
        headers=_auth(token),
        json={
            "key": "bed_preference",
            "value": "King",
            "source": "CUSTOMER_PROVIDED",
        },
    )
    assert created.status_code == 201, created.text
    preference = created.json()["data"]
    assert preference["source"] == "CUSTOMER_PROVIDED"
    updated = client_db.patch(
        f"{url}/{preference['id']}",
        headers=_auth(token),
        json={"value": "Twin", "source": "STAFF_CONFIRMED"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["value"] == "Twin"
    inferred = client_db.post(
        url,
        headers=_auth(token),
        json={
            "key": "language",
            "value": "Thai",
            "source": "AI_INFERRED",
        },
    )
    assert inferred.status_code == 422

    async def read():
        async with TestSessionLocal() as session:
            return list((await session.scalars(select(CustomerPreference))).all())

    rows = asyncio.run(read())
    assert [(row.key.value, row.value) for row in rows] == [("bed_preference", "Twin")]


def test_tag_normalization_assignment_removal_and_audit(client_db):
    _, token = register_verify_and_login(client_db, email="crm-tags@example.com")
    customer = _customer(client_db, token)
    first = client_db.post(
        "/api/v1/crm/tags", headers=_auth(token), json={"name": " VIP "}
    )
    second = client_db.post(
        "/api/v1/crm/tags", headers=_auth(token), json={"name": "vip"}
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    tag_id = first.json()["data"]["id"]
    assignment_url = f"/api/v1/crm/customers/{customer['id']}/tags/{tag_id}"
    assert client_db.post(assignment_url, headers=_auth(token)).status_code == 200
    assert client_db.post(assignment_url, headers=_auth(token)).status_code == 200
    detail = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}", headers=_auth(token)
    ).json()["data"]
    assert [tag["normalized_name"] for tag in detail["tags"]] == ["vip"]
    assert client_db.delete(assignment_url, headers=_auth(token)).status_code == 200

    async def read_events():
        async with TestSessionLocal() as session:
            return [
                event.event_type.value
                for event in (
                    await session.scalars(
                        select(CustomerCRMEvent).order_by(CustomerCRMEvent.created_at)
                    )
                ).all()
            ]

    assert asyncio.run(read_events()) == ["TAG_ADDED", "TAG_REMOVED"]


def test_cross_workspace_tag_and_customer_access_are_rejected(client_db):
    _, token_a = register_verify_and_login(client_db, email="crm-scope-a@example.com")
    customer_a = _customer(client_db, token_a, "Guest A")
    tag = client_db.post(
        "/api/v1/crm/tags", headers=_auth(token_a), json={"name": "VIP"}
    ).json()["data"]
    _, token_b = register_verify_and_login(client_db, email="crm-scope-b@example.com")
    customer_b = _customer(client_db, token_b, "Guest B")
    assert (
        client_db.post(
            f"/api/v1/crm/customers/{customer_b['id']}/tags/{tag['id']}",
            headers=_auth(token_b),
        ).status_code
        == 404
    )
    assert (
        client_db.get(
            f"/api/v1/crm/customers/{customer_a['id']}", headers=_auth(token_b)
        ).status_code
        == 404
    )


def test_staff_note_is_append_only_and_workspace_scoped(client_db):
    _, token = register_verify_and_login(client_db, email="crm-notes@example.com")
    customer = _customer(client_db, token)
    url = f"/api/v1/crm/customers/{customer['id']}/notes"
    for body in ("First note", "Second note"):
        response = client_db.post(url, headers=_auth(token), json={"body": body})
        assert response.status_code == 201, response.text
    detail = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}", headers=_auth(token)
    ).json()["data"]
    assert {note["body"] for note in detail["notes"]} == {
        "First note",
        "Second note",
    }
    assert detail["customer"]["id"] == customer["id"]


def test_member_can_add_note_and_preference_but_cannot_manage_tags(client_db):
    user, token = register_verify_and_login(client_db, email="crm-member@example.com")
    customer = _customer(client_db, token)

    async def demote():
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id
                    == uuid.UUID(user["workspace"]["id"]),
                    WorkspaceMember.user_id == uuid.UUID(user["user"]["id"]),
                )
            )
            assert membership is not None
            membership.role = WorkspaceRole.MEMBER
            session.add_all(
                WorkspaceMemberCapability(
                    workspace_id=membership.workspace_id,
                    membership_id=membership.id,
                    capability=capability,
                    granted_by_user_id=membership.user_id,
                    granted_at=datetime.now(UTC),
                )
                for capability in ("guest.note", "guest.preference.manage")
            )
            await session.commit()

    asyncio.run(demote())
    assert (
        client_db.post(
            f"/api/v1/crm/customers/{customer['id']}/notes",
            headers=_auth(token),
            json={"body": "Operational note"},
        ).status_code
        == 201
    )
    assert (
        client_db.post(
            f"/api/v1/crm/customers/{customer['id']}/preferences",
            headers=_auth(token),
            json={"key": "language", "value": "Thai"},
        ).status_code
        == 201
    )
    assert (
        client_db.post(
            "/api/v1/crm/tags", headers=_auth(token), json={"name": "VIP"}
        ).status_code
        == 403
    )


def test_customer_list_search_tag_filters_pagination_and_order(client_db):
    _, token = register_verify_and_login(client_db, email="crm-list@example.com")
    alpha = _customer(client_db, token, "Alpha Guest")
    _customer(client_db, token, "Beta Guest")
    tag = client_db.post(
        "/api/v1/crm/tags", headers=_auth(token), json={"name": "Corporate"}
    ).json()["data"]
    client_db.post(
        f"/api/v1/crm/customers/{alpha['id']}/tags/{tag['id']}",
        headers=_auth(token),
    )
    searched = client_db.get(
        "/api/v1/crm/customers?q=Alpha&page=1&page_size=1", headers=_auth(token)
    ).json()["data"]
    assert searched["total"] == 1
    assert searched["items"][0]["customer"]["display_name"] == "Alpha Guest"
    tagged = client_db.get(
        f"/api/v1/crm/customers?tag_id={tag['id']}", headers=_auth(token)
    ).json()["data"]
    assert [item["customer"]["id"] for item in tagged["items"]] == [alpha["id"]]
    assert tagged["items"][0]["tags"][0]["name"] == "Corporate"


def test_customer_list_operational_filters_use_authoritative_domains(client_db):
    user, token, prop, room, plan = _setup(
        client_db, email="crm-filters@example.com", units=2
    )
    customer = _customer(client_db, token, "Filter Guest")
    booking = _hold(
        client_db,
        token,
        _payload(prop, room, plan, key="crm-filter", customer_id=customer["id"]),
    )
    assert booking.status_code == 201, booking.text
    conversation_id = _conversation(client_db, token, customer["id"])

    async def mark_attention():
        async with TestSessionLocal() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .values(needs_attention=True)
            )
            await session.commit()

    asyncio.run(mark_attention())
    for query_name in ("has_active_booking", "needs_attention"):
        response = client_db.get(
            f"/api/v1/crm/customers?{query_name}=true", headers=_auth(token)
        )
        assert response.status_code == 200, response.text
        assert [
            item["customer"]["id"] for item in response.json()["data"]["items"]
        ] == [customer["id"]]
    assert user["workspace"]["id"]


@pytest.mark.parametrize(
    "statuses,expected",
    [
        ([BookingStatus.CONFIRMED], False),
        ([BookingStatus.CONFIRMED, BookingStatus.CONFIRMED], True),
        ([BookingStatus.CONFIRMED, BookingStatus.CANCELLED], False),
    ],
)
def test_repeat_guest_uses_confirmed_booking_count_only(client_db, statuses, expected):
    user, token, prop, room, plan = _setup(
        client_db,
        email=f"crm-repeat-{len(statuses)}-{statuses[-1]}@example.com",
        units=3,
    )
    customer = _customer(client_db, token)
    booking_ids = []
    for index, status in enumerate(statuses):
        response = _hold(
            client_db,
            token,
            _payload(
                prop,
                room,
                plan,
                key=f"repeat-{index}",
                customer_id=customer["id"],
            ),
        )
        assert response.status_code == 201, response.text
        booking_ids.append((uuid.UUID(response.json()["data"]["id"]), status))

    async def set_statuses():
        async with TestSessionLocal() as session:
            for booking_id, status in booking_ids:
                await session.execute(
                    update(Booking)
                    .where(Booking.id == booking_id)
                    .values(status=status)
                )
            await session.commit()

    asyncio.run(set_statuses())
    data = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}", headers=_auth(token)
    ).json()["data"]
    assert data["repeat_guest_summary"]["repeat_guest"] is expected
    assert data["repeat_guest_summary"]["confirmed_bookings"] == statuses.count(
        BookingStatus.CONFIRMED
    )
    filtered = client_db.get(
        f"/api/v1/crm/customers?repeat_guest={str(expected).lower()}",
        headers=_auth(token),
    )
    assert filtered.status_code == 200, filtered.text
    assert customer["id"] in {
        item["customer"]["id"] for item in filtered.json()["data"]["items"]
    }
    assert data["customer"]["id"] == customer["id"]
    assert user["workspace"]["id"]


def test_booking_payment_exception_and_safe_payment_history(client_db):
    _, token, booking, destination_id, _ = _prepared(
        client_db, email="crm-payment@example.com"
    )
    customer = _customer(client_db, token)

    async def link_customer():
        async with TestSessionLocal() as session:
            await session.execute(
                update(Booking)
                .where(Booking.id == uuid.UUID(booking["id"]))
                .values(customer_id=uuid.UUID(customer["id"]))
            )
            await session.commit()

    asyncio.run(link_customer())
    _advance(client_db, token, booking)
    payment = _link(client_db, token, booking, destination_id).json()["data"]
    _mark_verified(payment["id"], amount=Decimal("1.00"))
    reconciled = client_db.post(
        f"/api/v1/hotel/payment-exceptions/{payment['id']}/reconcile",
        headers=_auth(token),
    )
    assert reconciled.status_code == 200, reconciled.text
    response = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["bookings"][0]["id"] == booking["id"]
    assert data["payments"][0]["status"] == "VERIFIED"
    assert data["payment_exceptions"][0]["reason"] == "AMOUNT_MISMATCH"
    filtered = client_db.get(
        "/api/v1/crm/customers?has_payment_exception=true", headers=_auth(token)
    )
    assert filtered.status_code == 200, filtered.text
    assert [item["customer"]["id"] for item in filtered.json()["data"]["items"]] == [
        customer["id"]
    ]
    for secret_field in ("storage_key", "content_hash", "provider_response"):
        assert secret_field not in response.text


def test_applied_payment_is_history_not_an_exception(client_db):
    _, token, booking, destination_id, _ = _prepared(
        client_db, email="crm-applied-payment@example.com"
    )
    customer = _customer(client_db, token)

    async def link_customer():
        async with TestSessionLocal() as session:
            await session.execute(
                update(Booking)
                .where(Booking.id == uuid.UUID(booking["id"]))
                .values(customer_id=uuid.UUID(customer["id"]))
            )
            await session.commit()

    asyncio.run(link_customer())
    _advance(client_db, token, booking)
    payment = _link(client_db, token, booking, destination_id).json()["data"]
    _mark_verified(payment["id"])
    confirmed = _confirm(client_db, token, booking, payment["id"])
    assert confirmed.status_code == 200, confirmed.text
    data = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}", headers=_auth(token)
    ).json()["data"]
    assert data["payments"][0]["application_status"] == "APPLIED"
    assert data["payments"][0]["booking_applied_at"] is not None
    assert data["payment_exceptions"] == []


def test_timeline_is_deterministic_bounded_and_workspace_scoped(client_db):
    _, token = register_verify_and_login(client_db, email="crm-timeline@example.com")
    customer = _customer(client_db, token)
    client_db.post(
        f"/api/v1/crm/customers/{customer['id']}/notes",
        headers=_auth(token),
        json={"body": "Arrival after 20:00"},
    )
    client_db.post(
        f"/api/v1/crm/customers/{customer['id']}/preferences",
        headers=_auth(token),
        json={"key": "arrival_preference", "value": "After 20:00"},
    )
    response = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}/timeline?page=1&page_size=1",
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["items"]) == 1
    assert data["total"] == 2
    assert data["items"][0]["type"] in {"NOTE_ADDED", "PREFERENCE_ADDED"}
    assert "Arrival after 20:00" not in response.text
    _, other_token = register_verify_and_login(
        client_db, email="crm-timeline-other@example.com"
    )
    assert (
        client_db.get(
            f"/api/v1/crm/customers/{customer['id']}/timeline",
            headers=_auth(other_token),
        ).status_code
        == 404
    )
