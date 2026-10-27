"""F-A2: PAYMENT_VERIFIED only reaches people who may act on it.

The linked Action's assignee is notified only while they are still a member
holding payment.read, action.read and action.operate; otherwise owners and
admins are. Recipient problems never undo or block the verification itself.
"""

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

import app.services.payment as payment_module
from app.models.action import ActionEvent, ActionRequest
from app.models.audit import WorkspaceAuditEvent
from app.models.automation import DomainEventOutbox
from app.models.notification import Notification, NotificationType
from app.models.payment import Payment
from app.models.workspace_member import WorkspaceRole
from app.services.notification import NotificationService
from app.storage.local import LocalStorageProvider
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_actions import _create, _definition
from tests.test_payment_verification import _submit_and_verify
from tests.test_payments import _destination, _payment
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

FULL = ["action.read", "action.operate", "payment.read"]


@pytest.fixture(autouse=True)
def payment_storage(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        payment_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )


def _world(client, email):
    owner, token = register_verify_and_login(client, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    action = _create(client, headers, _definition(client, headers)).json()["data"]
    return {
        "owner_id": owner["user"]["id"],
        "workspace_id": owner["workspace"]["id"],
        "token": token,
        "headers": headers,
        "action": action["id"],
    }


def _member(client, world, email, capabilities, role=WorkspaceRole.MEMBER):
    user, _ = _zero_workspace_account(client, email)
    membership_id = _add_member(world["workspace_id"], user["id"], role)
    if role is WorkspaceRole.MEMBER:
        _grant(client, world, membership_id, capabilities)
    return user["id"], membership_id


def _grant(client, world, membership_id, capabilities):
    granted = client.put(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}/capabilities",
        headers=_headers(world["token"]),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text


def _assigned_payment(client, world, email):
    """An assignee with every needed capability, and a payment for their Action."""

    assignee_id, membership_id = _member(client, world, email, FULL)
    assigned = client.post(
        f"/api/v1/actions/{world['action']}/assign",
        headers=world["headers"],
        json={"user_id": assignee_id},
    )
    assert assigned.status_code == 200, assigned.text
    payment_id = _payment(
        client,
        world["headers"],
        _destination(client, world["headers"]),
        action_request_id=world["action"],
    ).json()["data"]["id"]
    return assignee_id, membership_id, payment_id


def _verified_recipients(world, payment_id):
    async def read():
        async with TestSessionLocal() as session:
            rows = await session.execute(
                select(
                    Notification.recipient_user_id,
                    Notification.title,
                    Notification.body,
                    Notification.entity_id,
                ).where(
                    Notification.workspace_id == uuid.UUID(world["workspace_id"]),
                    Notification.type == NotificationType.PAYMENT_VERIFIED,
                )
            )
            return rows.all()

    rows = asyncio.run(read())
    for _, title, body, entity_id in rows:
        assert str(entity_id) == payment_id
        # Generic text only: no amount, destination or guest details.
        for text in (title, body):
            assert "1234" not in text and "xxxx" not in text
    return sorted(str(row[0]) for row in rows)


def _verify(client, world, payment_id):
    response = _submit_and_verify(client, world["headers"], payment_id)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["payment"]["status"] == "VERIFIED"


def test_eligible_assignee_alone_is_notified(client_db):
    world = _world(client_db, "fa2-eligible@example.com")
    assignee_id, _, payment_id = _assigned_payment(
        client_db, world, "fa2-eligible-assignee@example.com"
    )
    _verify(client_db, world, payment_id)
    assert _verified_recipients(world, payment_id) == [assignee_id]


@pytest.mark.parametrize(
    "remaining",
    [
        ["action.read", "action.operate"],
        ["action.operate", "payment.read"],
        ["action.read", "payment.read"],
    ],
    ids=["without-payment-read", "without-action-read", "without-action-operate"],
)
def test_assignee_who_lost_a_capability_falls_back_to_admins(client_db, remaining):
    world = _world(
        client_db, f"fa2-revoked-{len(remaining)}-{remaining[0]}@example.com"
    )
    _, membership_id, payment_id = _assigned_payment(
        client_db, world, f"fa2-revoked-assignee-{remaining[-1]}@example.com"
    )
    _grant(client_db, world, membership_id, remaining)
    _verify(client_db, world, payment_id)
    assert _verified_recipients(world, payment_id) == [world["owner_id"]]


def test_removed_assignee_is_not_notified(client_db):
    world = _world(client_db, "fa2-removed@example.com")
    _, membership_id, payment_id = _assigned_payment(
        client_db, world, "fa2-removed-assignee@example.com"
    )
    removed = client_db.delete(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}",
        headers=_headers(world["token"]),
    )
    assert removed.status_code in {200, 204}, removed.text
    _verify(client_db, world, payment_id)
    admin_id, _ = _member(
        client_db, world, "fa2-removed-admin@example.com", [], WorkspaceRole.ADMIN
    )
    # Recipients are read when the payment verifies; the admin added later
    # is not retroactively notified.
    assert admin_id not in _verified_recipients(world, payment_id)
    assert _verified_recipients(world, payment_id) == [world["owner_id"]]


def test_owner_and_admin_both_back_up_an_ineligible_assignee(client_db):
    world = _world(client_db, "fa2-backup@example.com")
    admin_id, _ = _member(
        client_db, world, "fa2-backup-admin@example.com", [], WorkspaceRole.ADMIN
    )
    _, membership_id, payment_id = _assigned_payment(
        client_db, world, "fa2-backup-assignee@example.com"
    )
    _grant(client_db, world, membership_id, ["action.read", "action.operate"])
    _verify(client_db, world, payment_id)
    assert _verified_recipients(world, payment_id) == sorted(
        [world["owner_id"], admin_id]
    )


def _payment_state(world, payment_id):
    async def read():
        async with TestSessionLocal() as session:
            scope = uuid.UUID(world["workspace_id"])
            payment = await session.get(Payment, uuid.UUID(payment_id))
            action = await session.get(ActionRequest, uuid.UUID(world["action"]))

            async def count(model, *conditions):
                return await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.workspace_id == scope, *conditions)
                )

            return {
                "payment": (payment.status.value, str(payment.verified_amount)),
                "action": (action.status.value, str(action.assigned_to_user_id)),
                "action_events": await count(ActionEvent),
                "verified_audit": await count(
                    WorkspaceAuditEvent,
                    WorkspaceAuditEvent.action == "PAYMENT_VERIFIED",
                ),
                "verified_events": await count(
                    DomainEventOutbox,
                    DomainEventOutbox.event_type == "hotel.payment.verified",
                ),
            }

    return asyncio.run(read())


def test_no_eligible_recipient_never_blocks_verification(client_db, monkeypatch):
    world = _world(client_db, "fa2-nobody@example.com")
    assignee_id, membership_id, payment_id = _assigned_payment(
        client_db, world, "fa2-nobody-assignee@example.com"
    )
    _grant(client_db, world, membership_id, ["action.read"])
    before = _payment_state(world, payment_id)

    async def no_admins(self, workspace_id):
        return []

    monkeypatch.setattr(NotificationService, "administrative_recipients", no_admins)
    _verify(client_db, world, payment_id)
    after = _payment_state(world, payment_id)
    assert _verified_recipients(world, payment_id) == []
    # The verification stands and stays observable through audit and the
    # domain event outbox; the Action itself is untouched.
    assert after["payment"] == ("VERIFIED", "1234.50")
    assert after["verified_audit"] == before["verified_audit"] + 1
    assert after["verified_events"] == before["verified_events"] + 1
    assert after["action"] == before["action"] == ("ASSIGNED", assignee_id)
    assert after["action_events"] == before["action_events"]


def test_repeated_verification_does_not_duplicate_the_notice(client_db):
    world = _world(client_db, "fa2-retry@example.com")
    assignee_id, _, payment_id = _assigned_payment(
        client_db, world, "fa2-retry-assignee@example.com"
    )
    _verify(client_db, world, payment_id)
    again = client_db.post(
        f"/api/v1/payments/{payment_id}/verify", headers=world["headers"]
    )
    assert again.status_code in {200, 409}, again.text
    assert _verified_recipients(world, payment_id) == [assignee_id]
