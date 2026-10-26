"""CRM Customer360 must not expose payment data without payment.read.

guest.read keeps access to the guest profile, while payments, payment
exceptions, payment timeline events, and the payment-exception list flag and
filter require payment.read. Denials and hidden sections cause no writes.
"""

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import func, select, update

from app.models.audit import WorkspaceAuditEvent
from app.models.booking import Booking
from app.models.payment import Payment
from app.models.workspace_member import WorkspaceRole
from tests.conftest import TestSessionLocal
from tests.test_booking_payment_confirmation import (
    _advance,
    _link,
    _mark_verified,
    _prepared,
)
from tests.test_crm import _customer
from tests.test_hotel import _auth
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

GUEST_EMAIL = "abc.guest@example.com"
GUEST_PHONE = "+66812345678"


def _payment_customer(client, email):
    """Owner Workspace with a customer whose booking has a payment exception."""

    owner, token, booking, destination_id, _ = _prepared(client, email=email)
    customer = _customer(client, token)

    async def link_customer():
        async with TestSessionLocal() as session:
            await session.execute(
                update(Booking)
                .where(Booking.id == uuid.UUID(booking["id"]))
                .values(customer_id=uuid.UUID(customer["id"]))
            )
            await session.commit()

    asyncio.run(link_customer())
    _advance(client, token, booking)
    payment = _link(client, token, booking, destination_id).json()["data"]
    _mark_verified(payment["id"], amount=Decimal("1.00"))
    reconciled = client.post(
        f"/api/v1/hotel/payment-exceptions/{payment['id']}/reconcile",
        headers=_auth(token),
    )
    assert reconciled.status_code == 200, reconciled.text
    return owner, token, customer, payment["id"]


def _member(client, owner_token, workspace_id, email, capabilities):
    user, token = _zero_workspace_account(client, email)
    membership_id = _add_member(workspace_id, user["id"], WorkspaceRole.MEMBER)
    granted = client.put(
        f"/api/v1/workspaces/{workspace_id}/members/{membership_id}/capabilities",
        headers=_headers(owner_token),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text
    return _headers(token, workspace_id)


def _state(workspace_id: str, payment_id: str):
    async def read():
        async with TestSessionLocal() as session:
            payment = await session.get(Payment, uuid.UUID(payment_id))
            audit = await session.scalar(
                select(func.count())
                .select_from(WorkspaceAuditEvent)
                .where(WorkspaceAuditEvent.workspace_id == uuid.UUID(workspace_id))
            )
            return (
                payment.status,
                payment.booking_application_status,
                payment.booking_review_note,
                payment.updated_at,
                audit,
            )

    return asyncio.run(read())


def _assert_no_payment_data(text: str, payment_id: str):
    assert payment_id not in text
    assert "AMOUNT_MISMATCH" not in text


def test_guest_read_member_sees_profile_but_no_payment_data(client_db):
    owner, owner_token, customer, payment_id = _payment_customer(
        client_db, "crm-visibility-owner@example.com"
    )
    workspace_id = owner["workspace"]["id"]
    member = _member(
        client_db,
        owner_token,
        workspace_id,
        "crm-guest-reader@example.com",
        ["guest.read"],
    )
    before = _state(workspace_id, payment_id)

    detail = client_db.get(f"/api/v1/crm/customers/{customer['id']}", headers=member)
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    # The guest profile stays readable under guest.read.
    assert data["customer"]["id"] == customer["id"]
    assert data["customer"]["email"] == GUEST_EMAIL
    assert data["payments"] == []
    assert data["payment_exceptions"] == []
    _assert_no_payment_data(detail.text, payment_id)
    assert data["payments_visible"] is False

    timeline = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}/timeline", headers=member
    )
    assert timeline.status_code == 200, timeline.text
    timeline_data = timeline.json()["data"]
    assert timeline_data["payments_visible"] is False
    assert all(item["entity_type"] != "payment" for item in timeline_data["items"])
    assert payment_id not in timeline.text

    listing = client_db.get("/api/v1/crm/customers", headers=member)
    assert listing.status_code == 200, listing.text
    listed = listing.json()["data"]
    assert listed["payments_visible"] is False
    assert [item["has_payment_exception"] for item in listed["items"]] == [None]

    filtered = client_db.get(
        "/api/v1/crm/customers?has_payment_exception=true", headers=member
    )
    assert filtered.status_code == 403, filtered.text
    assert filtered.json()["error"]["code"] == "FORBIDDEN"
    for value in (GUEST_EMAIL, GUEST_PHONE, payment_id):
        assert value not in filtered.text

    # Reads and denials write nothing and record no audit event.
    assert _state(workspace_id, payment_id) == before


def test_payment_read_member_sees_payment_data(client_db):
    owner, owner_token, customer, payment_id = _payment_customer(
        client_db, "crm-payments-owner@example.com"
    )
    workspace_id = owner["workspace"]["id"]
    member = _member(
        client_db,
        owner_token,
        workspace_id,
        "crm-payment-reader@example.com",
        ["guest.read", "payment.read"],
    )
    detail = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}", headers=member
    ).json()["data"]
    assert detail["payments_visible"] is True
    assert [item["id"] for item in detail["payments"]] == [payment_id]
    assert detail["payment_exceptions"][0]["payment_id"] == payment_id
    assert detail["payment_exceptions"][0]["reason"] == "AMOUNT_MISMATCH"

    timeline = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}/timeline", headers=member
    ).json()["data"]
    assert timeline["payments_visible"] is True
    assert any(item["entity_id"] == payment_id for item in timeline["items"])

    listed = client_db.get(
        "/api/v1/crm/customers?has_payment_exception=true", headers=member
    )
    assert listed.status_code == 200, listed.text
    assert [item["customer"]["id"] for item in listed.json()["data"]["items"]] == [
        customer["id"]
    ]
    assert listed.json()["data"]["items"][0]["has_payment_exception"] is True


def test_customer360_ids_from_another_workspace_do_not_leak(client_db):
    owner, _, customer, payment_id = _payment_customer(
        client_db, "crm-leak-owner@example.com"
    )
    _, other_token, *_ = _prepared(client_db, email="crm-leak-other@example.com")
    before = _state(owner["workspace"]["id"], payment_id)
    other = _auth(other_token)
    for path in (
        f"/api/v1/crm/customers/{customer['id']}",
        f"/api/v1/crm/customers/{customer['id']}/timeline",
    ):
        response = client_db.get(path, headers=other)
        assert response.status_code == 404, response.text
        for value in (GUEST_EMAIL, GUEST_PHONE, payment_id, "AMOUNT_MISMATCH"):
            assert value not in response.text
    listing = client_db.get("/api/v1/crm/customers", headers=other).json()["data"]
    assert customer["id"] not in {item["customer"]["id"] for item in listing["items"]}
    forged = client_db.get(
        f"/api/v1/crm/customers/{customer['id']}",
        headers={**other, "X-Workspace-ID": owner["workspace"]["id"]},
    )
    assert forged.status_code == 403, forged.text
    assert payment_id not in forged.text and GUEST_EMAIL not in forged.text
    assert _state(owner["workspace"]["id"], payment_id) == before
