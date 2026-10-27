"""H2: payment routes follow payment.read and payment.review.

Reads need payment.read. Changes (destinations, payments, evidence,
verification) need payment.review and payment.read, because every change
returns the payment it touched. Linking a customer, conversation or Action to
a payment needs guest.read, conversation.read or action.read, checked before
the id is looked up.
"""

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

import app.services.payment as payment_module
from app.models.audit import WorkspaceAuditEvent
from app.models.payment import Payment, PaymentDestination, PaymentEvidence
from app.models.workspace_member import WorkspaceRole
from app.storage.local import LocalStorageProvider
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_actions import _create as _create_action
from tests.test_actions import _definition
from tests.test_crm import _conversation, _customer
from tests.test_payments import JPEG, URL, _destination, _payment
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

EXPECTED_AMOUNT = "1234.50"


@pytest.fixture(autouse=True)
def payment_storage(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        payment_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )


def _world(client, email):
    owner, token = register_verify_and_login(client, email=email)
    headers = _headers(token)
    destination = _destination(client, headers)
    customer = _customer(client, token)
    payment = _payment(client, headers, destination, customer_id=customer["id"])
    assert payment.status_code == 201, payment.text
    payment_id = payment.json()["data"]["id"]
    evidence = client.post(
        f"{URL}/{payment_id}/evidence",
        headers=headers,
        files={"file": ("slip.jpg", JPEG, "image/jpeg")},
    )
    assert evidence.status_code == 201, evidence.text
    return {
        "workspace_id": owner["workspace"]["id"],
        "token": token,
        "headers": headers,
        "destination": destination,
        "customer": customer["id"],
        "conversation": _conversation(client, token, customer["id"]),
        "action": _create_action(client, headers, _definition(client, headers)).json()[
            "data"
        ]["id"],
        "payment": payment_id,
    }


def _member(client, world, email, capabilities):
    user, token = _zero_workspace_account(client, email)
    membership_id = _add_member(world["workspace_id"], user["id"], WorkspaceRole.MEMBER)
    granted = client.put(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}/capabilities",
        headers=_headers(world["token"]),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text
    return _headers(token, world["workspace_id"])


def _state(world):
    async def read():
        async with TestSessionLocal() as session:
            scope = uuid.UUID(world["workspace_id"])

            async def rows(model, *columns):
                result = await session.execute(
                    select(*columns)
                    .where(model.workspace_id == scope)
                    .order_by(*columns)
                )
                return [tuple(row) for row in result.all()]

            return {
                "payments": await rows(
                    Payment, Payment.id, Payment.status, Payment.updated_at
                ),
                "destinations": await rows(
                    PaymentDestination,
                    PaymentDestination.id,
                    PaymentDestination.is_active,
                    PaymentDestination.updated_at,
                ),
                "evidence": await rows(PaymentEvidence, PaymentEvidence.id),
                "audit": await session.scalar(
                    select(func.count())
                    .select_from(WorkspaceAuditEvent)
                    .where(WorkspaceAuditEvent.workspace_id == scope)
                ),
            }

    return asyncio.run(read())


def _reads(world):
    payment = world["payment"]
    return [
        ("get", f"{URL}/destinations", None),
        ("get", URL, None),
        ("get", f"{URL}/{payment}", None),
        ("get", f"{URL}/{payment}/evidence", None),
        ("get", f"{URL}/{payment}/verifications", None),
    ]


def _changes(world):
    payment = world["payment"]
    return [
        (
            "post",
            f"{URL}/destinations",
            {
                "type": "BANK_ACCOUNT",
                "display_name": "X",
                "account_number_masked": "x1",
            },
        ),
        ("patch", f"{URL}/destinations/{world['destination']}", {"is_active": False}),
        (
            "post",
            URL,
            {
                "payment_destination_id": world["destination"],
                "expected_amount": "10.00",
            },
        ),
        ("post", f"{URL}/{payment}/verify", None),
    ]


def _send(client, method, path, body, headers):
    if body is None:
        return getattr(client, method)(path, headers=headers)
    return getattr(client, method)(path, headers=headers, json=body)


def _assert_denied(client, world, headers, requests, capability):
    for method, path, body in requests:
        response = _send(client, method, path, body, headers)
        assert response.status_code == 403, (path, response.text)
        assert capability in response.json()["message"], path
        assert EXPECTED_AMOUNT not in response.text
        assert world["customer"] not in response.text


def test_member_without_payment_capabilities_is_denied(client_db):
    world = _world(client_db, "h2-none-owner@example.com")
    member = _member(client_db, world, "h2-none@example.com", [])
    before = _state(world)
    _assert_denied(client_db, world, member, _reads(world), "payment.read")
    _assert_denied(client_db, world, member, _changes(world), "payment.review")
    evidence = client_db.post(
        f"{URL}/{world['payment']}/evidence",
        headers=member,
        files={"file": ("slip.jpg", JPEG, "image/jpeg")},
    )
    assert evidence.status_code == 403, evidence.text
    assert _state(world) == before


def test_payment_reader_reads_but_cannot_change(client_db):
    world = _world(client_db, "h2-read-owner@example.com")
    member = _member(client_db, world, "h2-reader@example.com", ["payment.read"])
    before = _state(world)
    detail = client_db.get(f"{URL}/{world['payment']}", headers=member)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["expected_amount"] == EXPECTED_AMOUNT
    for method, path, body in _reads(world):
        assert _send(client_db, method, path, body, member).status_code == 200, path
    _assert_denied(client_db, world, member, _changes(world), "payment.review")
    assert _state(world) == before


def test_reviewer_without_read_cannot_change_or_read_through_responses(client_db):
    world = _world(client_db, "h2-review-owner@example.com")
    member = _member(client_db, world, "h2-reviewer@example.com", ["payment.review"])
    before = _state(world)
    _assert_denied(client_db, world, member, _reads(world), "payment.read")
    _assert_denied(client_db, world, member, _changes(world), "payment.read")
    evidence = client_db.post(
        f"{URL}/{world['payment']}/evidence",
        headers=member,
        files={"file": ("slip.jpg", JPEG, "image/jpeg")},
    )
    assert evidence.status_code == 403, evidence.text
    assert _state(world) == before


def test_linking_records_needs_their_read_capability(client_db):
    world = _world(client_db, "h2-link-owner@example.com")
    member = _member(
        client_db, world, "h2-linker@example.com", ["payment.read", "payment.review"]
    )
    missing = str(uuid.uuid4())
    before = _state(world)
    for field, real, capability in (
        ("customer_id", world["customer"], "guest.read"),
        ("conversation_id", world["conversation"], "conversation.read"),
        ("action_request_id", world["action"], "action.read"),
    ):
        bodies = set()
        for value in (real, missing):
            response = client_db.post(
                URL,
                headers=member,
                json={
                    "payment_destination_id": world["destination"],
                    "expected_amount": "10.00",
                    field: value,
                },
            )
            assert response.status_code == 403, response.text
            assert capability in response.json()["message"]
            bodies.add(response.text)
        # Existing and missing ids are indistinguishable.
        assert len(bodies) == 1
    assert _state(world) == before
    plain = client_db.post(
        URL,
        headers=member,
        json={
            "payment_destination_id": world["destination"],
            "expected_amount": "10.00",
        },
    )
    assert plain.status_code == 201, plain.text


def test_payments_stay_inside_their_workspace(client_db):
    world = _world(client_db, "h2-tenant-a@example.com")
    _, other_token = register_verify_and_login(
        client_db, email="h2-tenant-b@example.com"
    )
    other = _headers(other_token)
    before = _state(world)
    for method, path, body in _reads(world)[2:] + [
        ("post", f"{URL}/{world['payment']}/verify", None)
    ]:
        response = _send(client_db, method, path, body, other)
        assert response.status_code == 404, (path, response.text)
        assert EXPECTED_AMOUNT not in response.text
    forged = client_db.get(
        f"{URL}/{world['payment']}",
        headers={**other, "X-Workspace-ID": world["workspace_id"]},
    )
    assert forged.status_code == 403, forged.text
    assert _state(world) == before
