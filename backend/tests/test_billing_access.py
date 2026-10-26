"""F-D1: Workspace billing data needs workspace.billing.read.

Owners and admins hold it through the role baseline; members need a grant.
Members holding payment.read still see their slip-verification quota (the
Payments page shows it) and nothing else. A member without the grant sees no
Workspace subscription; their own billing account stays visible to them.
"""

import asyncio
import uuid

from sqlalchemy import func, select

from app.models.audit import WorkspaceAuditEvent
from app.models.billing import SaaSUsageRecord, WorkspaceSubscription
from app.models.workspace_member import WorkspaceRole
from app.services.entitlement import SLIP_VERIFICATIONS
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

ENTITLEMENTS = "/api/v1/billing/entitlements"
USAGE = "/api/v1/billing/usage"
SUBSCRIPTION = "/api/v1/billing/subscription"


def _world(client, email):
    owner, token = register_verify_and_login(client, email=email)
    headers = _headers(token)
    subscription = client.get(SUBSCRIPTION, headers=headers).json()["data"]
    assert subscription and subscription["workspace_id"] == owner["workspace"]["id"]
    return {
        "workspace_id": owner["workspace"]["id"],
        "token": token,
        "headers": headers,
        "subscription": subscription,
    }


def _member(client, world, email, capabilities, role=WorkspaceRole.MEMBER):
    user, token = _zero_workspace_account(client, email)
    membership_id = _add_member(world["workspace_id"], user["id"], role)
    if role is WorkspaceRole.MEMBER:
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
    async def read():
        async with TestSessionLocal() as session:
            scope = uuid.UUID(world["workspace_id"])

            async def count(model):
                return await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.workspace_id == scope)
                )

            return (
                await count(WorkspaceSubscription),
                await count(SaaSUsageRecord),
                await count(WorkspaceAuditEvent),
            )

    return asyncio.run(read())


def _secrets(world):
    subscription = world["subscription"]
    return (
        subscription["id"],
        str(subscription["billing_account_id"]),
        subscription["plan"]["key"],
    )


def _assert_billing_hidden(response, world):
    for value in _secrets(world):
        if value and value != "None":
            assert value not in response.text, value


def test_member_without_billing_read_sees_no_workspace_billing(client_db):
    world = _world(client_db, "fd1-owner@example.com")
    member, _ = _member(client_db, world, "fd1-member@example.com", [])
    before = _state(world)
    for path in (ENTITLEMENTS, USAGE):
        response = client_db.get(path, headers=member)
        assert response.status_code == 403, response.text
        assert "workspace.billing.read" in response.json()["message"]
        _assert_billing_hidden(response, world)
    subscription = client_db.get(SUBSCRIPTION, headers=member)
    assert subscription.status_code == 200, subscription.text
    assert subscription.json()["data"] is None
    _assert_billing_hidden(subscription, world)
    assert _state(world) == before


def test_payment_reader_sees_only_the_slip_quota(client_db):
    world = _world(client_db, "fd1-pay-owner@example.com")
    owner_usage = client_db.get(USAGE, headers=world["headers"]).json()["data"]
    assert len(owner_usage) > 1
    member, _ = _member(client_db, world, "fd1-payments@example.com", ["payment.read"])
    usage = client_db.get(USAGE, headers=member)
    assert usage.status_code == 200, usage.text
    assert [item["key"] for item in usage.json()["data"]] == [SLIP_VERIFICATIONS]
    slip = next(item for item in owner_usage if item["key"] == SLIP_VERIFICATIONS)
    assert usage.json()["data"] == [slip]
    assert client_db.get(ENTITLEMENTS, headers=member).status_code == 403
    assert client_db.get(SUBSCRIPTION, headers=member).json()["data"] is None


def test_billing_readers_owner_and_admin_see_everything_until_revoked(client_db):
    world = _world(client_db, "fd1-read-owner@example.com")
    reader, membership_id = _member(
        client_db, world, "fd1-reader@example.com", ["workspace.billing.read"]
    )
    admin, _ = _member(
        client_db, world, "fd1-admin@example.com", [], WorkspaceRole.ADMIN
    )
    # Read after the members join: seat usage counts them.
    owner_view = {
        path: client_db.get(path, headers=world["headers"]).json()["data"]
        for path in (ENTITLEMENTS, USAGE)
    }
    for headers in (reader, admin):
        for path in (ENTITLEMENTS, USAGE):
            response = client_db.get(path, headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["data"] == owner_view[path]
        subscription = client_db.get(SUBSCRIPTION, headers=headers).json()["data"]
        assert subscription["id"] == world["subscription"]["id"]
    _grant(client_db, world, membership_id, [])
    for path in (ENTITLEMENTS, USAGE):
        assert client_db.get(path, headers=reader).status_code == 403
    assert client_db.get(SUBSCRIPTION, headers=reader).json()["data"] is None


def test_billing_stays_inside_each_workspace(client_db):
    first = _world(client_db, "fd1-first@example.com")
    second = _world(client_db, "fd1-second@example.com")
    forged = client_db.get(
        USAGE,
        headers={**second["headers"], "X-Workspace-ID": first["workspace_id"]},
    )
    assert forged.status_code == 403, forged.text
    own = client_db.get(SUBSCRIPTION, headers=second["headers"]).json()["data"]
    assert own["id"] == second["subscription"]["id"]
    assert first["subscription"]["id"] not in str(own)
