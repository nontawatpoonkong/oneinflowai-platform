"""Security regressions for F1 (role escalation), F2 (customer API capability),
and F3 (payment-exception capability).

Every denial asserts status and error code, unchanged persisted state, and the
absence of any audit event that would suggest the operation succeeded.
"""

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.models.audit import WorkspaceAuditEvent
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.workspace_access import (
    WorkspaceAccessAuditEvent,
    WorkspaceAccessRequest,
    WorkspaceMemberCapability,
)
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from tests.conftest import TestSessionLocal
from tests.test_booking_payment_reconciliation import (
    _exceptions,
    _retry,
    _scenario,
)
from tests.test_booking_payment_reconciliation import (
    _mark_verified as _mark_payment_verified,
)
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _join_code,
    _owner,
    _request,
    _zero_workspace_account,
)

# ---------------------------------------------------------------- helpers


def _snapshot(workspace_id: str) -> dict:
    """Persisted access state plus audit counts for one Workspace."""

    workspace = uuid.UUID(workspace_id)

    async def read():
        async with TestSessionLocal() as session:
            roles = {
                str(user_id): role.value
                for user_id, role in (
                    await session.execute(
                        select(WorkspaceMember.user_id, WorkspaceMember.role).where(
                            WorkspaceMember.workspace_id == workspace
                        )
                    )
                ).all()
            }
            grants = sorted(
                (str(membership_id), capability)
                for membership_id, capability in (
                    await session.execute(
                        select(
                            WorkspaceMemberCapability.membership_id,
                            WorkspaceMemberCapability.capability,
                        ).where(WorkspaceMemberCapability.workspace_id == workspace)
                    )
                ).all()
            )
            requests = sorted(
                (str(item_id), status.value)
                for item_id, status in (
                    await session.execute(
                        select(
                            WorkspaceAccessRequest.id, WorkspaceAccessRequest.status
                        ).where(WorkspaceAccessRequest.workspace_id == workspace)
                    )
                ).all()
            )
            access_audit = await session.scalar(
                select(func.count())
                .select_from(WorkspaceAccessAuditEvent)
                .where(WorkspaceAccessAuditEvent.workspace_id == workspace)
            )
            audit = await session.scalar(
                select(func.count())
                .select_from(WorkspaceAuditEvent)
                .where(WorkspaceAuditEvent.workspace_id == workspace)
            )
            return {
                "roles": roles,
                "grants": grants,
                "requests": requests,
                "access_audit": access_audit,
                "audit": audit,
            }

    return asyncio.run(read())


def _assert_forbidden(response):
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"


def _membership_id(workspace_id: str, user_id: str) -> str:
    async def read():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(WorkspaceMember.id).where(
                    WorkspaceMember.workspace_id == uuid.UUID(workspace_id),
                    WorkspaceMember.user_id == uuid.UUID(user_id),
                )
            )

    return str(asyncio.run(read()))


def _grant(client, owner_token, workspace_id, membership_id, capabilities):
    response = client.put(
        f"/api/v1/workspaces/{workspace_id}/members/{membership_id}/capabilities",
        headers=_headers(owner_token),
        json={"capabilities": capabilities},
    )
    assert response.status_code == 200, response.text


def _team(client):
    """Owner, a MEMBER holding workspace.members.manage, a plain MEMBER, and
    two ADMINs in one Workspace."""

    owner, owner_token = _owner(client, "f1-owner@access.example")
    workspace_id = owner["workspace"]["id"]
    accounts = {}
    for key, role in (
        ("manager", WorkspaceRole.MEMBER),
        ("member", WorkspaceRole.MEMBER),
        ("admin", WorkspaceRole.ADMIN),
        ("admin2", WorkspaceRole.ADMIN),
    ):
        user, token = _zero_workspace_account(client, f"f1-{key}@access.example")
        membership_id = _add_member(workspace_id, user["id"], role)
        accounts[key] = {"user": user, "token": token, "membership": membership_id}
    _grant(
        client,
        owner_token,
        workspace_id,
        accounts["manager"]["membership"],
        ["workspace.members.manage", "workspace.members.read"],
    )
    return owner, owner_token, workspace_id, accounts


# ------------------------------------------------------------------- F1


def test_f1_member_manager_cannot_create_or_manage_admins(client_db):
    _, owner_token, workspace_id, accounts = _team(client_db)
    manager = _headers(accounts["manager"]["token"])
    base = f"/api/v1/workspaces/{workspace_id}/members"
    before = _snapshot(workspace_id)

    # 1. Promote a plain MEMBER to ADMIN.
    _assert_forbidden(
        client_db.patch(
            f"{base}/{accounts['member']['membership']}",
            headers=manager,
            json={"role": "admin"},
        )
    )
    # 2. Demote, re-grant, or remove an ADMIN.
    _assert_forbidden(
        client_db.patch(
            f"{base}/{accounts['admin']['membership']}",
            headers=manager,
            json={"role": "member"},
        )
    )
    _assert_forbidden(
        client_db.put(
            f"{base}/{accounts['admin']['membership']}/capabilities",
            headers=manager,
            json={"capabilities": []},
        )
    )
    _assert_forbidden(
        client_db.delete(f"{base}/{accounts['admin']['membership']}", headers=manager)
    )
    assert _snapshot(workspace_id) == before

    # 3. Approve an access request as ADMIN.
    owner = {"workspace": {"id": workspace_id}}
    _, applicant_token = _zero_workspace_account(
        client_db, "f1-applicant@access.example"
    )
    request = _request(
        client_db, applicant_token, _join_code(client_db, owner, owner_token)
    ).json()["data"]
    pending = _snapshot(workspace_id)
    _assert_forbidden(
        client_db.post(
            f"/api/v1/workspaces/{workspace_id}/access-requests/"
            f"{request['id']}/approve",
            headers=manager,
            json={"role": "admin", "capabilities": []},
        )
    )
    assert _snapshot(workspace_id) == pending

    # The delegated manager still manages plain MEMBERs within its own grants.
    allowed = client_db.put(
        f"{base}/{accounts['member']['membership']}/capabilities",
        headers=manager,
        json={"capabilities": ["workspace.members.read"]},
    )
    assert allowed.status_code == 200, allowed.text
    approved = client_db.post(
        f"/api/v1/workspaces/{workspace_id}/access-requests/{request['id']}/approve",
        headers=manager,
        json={"role": "member", "capabilities": []},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["role"] == "member"


def test_f1_admin_cannot_appoint_or_manage_other_admins(client_db):
    _, owner_token, workspace_id, accounts = _team(client_db)
    admin = _headers(accounts["admin"]["token"])
    base = f"/api/v1/workspaces/{workspace_id}/members"
    before = _snapshot(workspace_id)

    _assert_forbidden(
        client_db.patch(
            f"{base}/{accounts['member']['membership']}",
            headers=admin,
            json={"role": "admin"},
        )
    )
    _assert_forbidden(
        client_db.patch(
            f"{base}/{accounts['admin2']['membership']}",
            headers=admin,
            json={"role": "member"},
        )
    )
    _assert_forbidden(
        client_db.delete(f"{base}/{accounts['admin2']['membership']}", headers=admin)
    )
    # Self-change and owner protection keep their existing outcomes.
    _assert_forbidden(
        client_db.patch(
            f"{base}/{accounts['admin']['membership']}",
            headers=admin,
            json={"role": "member"},
        )
    )
    assert _snapshot(workspace_id) == before

    owner = {"workspace": {"id": workspace_id}}
    _, applicant_token = _zero_workspace_account(
        client_db, "f1-admin-applicant@access.example"
    )
    request = _request(
        client_db, applicant_token, _join_code(client_db, owner, owner_token)
    ).json()["data"]
    pending = _snapshot(workspace_id)
    _assert_forbidden(
        client_db.post(
            f"/api/v1/workspaces/{workspace_id}/access-requests/"
            f"{request['id']}/approve",
            headers=admin,
            json={"role": "admin", "capabilities": []},
        )
    )
    assert _snapshot(workspace_id) == pending

    # ADMIN still manages plain MEMBERs.
    allowed = client_db.put(
        f"{base}/{accounts['member']['membership']}/capabilities",
        headers=admin,
        json={"capabilities": ["guest.read"]},
    )
    assert allowed.status_code == 200, allowed.text


def test_f1_owner_keeps_admin_authority(client_db):
    owner, owner_token, workspace_id, accounts = _team(client_db)
    headers = _headers(owner_token)
    base = f"/api/v1/workspaces/{workspace_id}/members"

    promoted = client_db.patch(
        f"{base}/{accounts['member']['membership']}",
        headers=headers,
        json={"role": "admin"},
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["data"]["role"] == "admin"
    demoted = client_db.patch(
        f"{base}/{accounts['admin2']['membership']}",
        headers=headers,
        json={"role": "member"},
    )
    assert demoted.status_code == 200, demoted.text
    removed = client_db.delete(
        f"{base}/{accounts['admin']['membership']}", headers=headers
    )
    assert removed.status_code == 200, removed.text

    _, applicant_token = _zero_workspace_account(
        client_db, "f1-owner-applicant@access.example"
    )
    request = _request(
        client_db, applicant_token, _join_code(client_db, owner, owner_token)
    ).json()["data"]
    approved = client_db.post(
        f"/api/v1/workspaces/{workspace_id}/access-requests/{request['id']}/approve",
        headers=headers,
        json={"role": "admin", "capabilities": []},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["role"] == "admin"

    roles = _snapshot(workspace_id)["roles"]
    assert roles[accounts["member"]["user"]["id"]] == "admin"
    assert roles[accounts["admin2"]["user"]["id"]] == "member"
    assert accounts["admin"]["user"]["id"] not in roles


# ------------------------------------------------------------------- F2


def _customers(workspace_id: str) -> list[tuple]:
    async def read():
        async with TestSessionLocal() as session:
            return sorted(
                (
                    str(item.id),
                    item.display_name,
                    item.email,
                    item.phone,
                    item.deleted_at,
                )
                for item in await session.scalars(
                    select(Customer).where(
                        Customer.workspace_id == uuid.UUID(workspace_id)
                    )
                )
            )

    return asyncio.run(read())


def _customer_audit(workspace_id: str) -> list[WorkspaceAuditEvent]:
    async def read():
        async with TestSessionLocal() as session:
            return list(
                await session.scalars(
                    select(WorkspaceAuditEvent)
                    .where(
                        WorkspaceAuditEvent.workspace_id == uuid.UUID(workspace_id),
                        WorkspaceAuditEvent.resource_type == "Customer",
                    )
                    .order_by(WorkspaceAuditEvent.occurred_at)
                )
            )

    return asyncio.run(read())


PII = {
    "display_name": "Secret Guest",
    "full_name": "Secret Guest Fullname",
    "email": "secret.guest@example.com",
    "phone": "+66899999999",
}


def test_f2_customer_routes_require_capabilities(client_db):
    owner, owner_token = _owner(client_db, "f2-owner@access.example")
    workspace_id = owner["workspace"]["id"]
    created = client_db.post(
        "/api/v1/customers", headers=_headers(owner_token), json=PII
    )
    assert created.status_code == 201, created.text
    customer_id = created.json()["data"]["id"]
    user, token = _zero_workspace_account(client_db, "f2-member@access.example")
    membership_id = _add_member(workspace_id, user["id"], WorkspaceRole.MEMBER)
    member = _headers(token, workspace_id)
    before = (_customers(workspace_id), _snapshot(workspace_id))

    calls = [
        ("get", "/api/v1/customers", None),
        ("get", f"/api/v1/customers/{customer_id}", None),
        ("post", "/api/v1/customers", {"display_name": "Injected"}),
        ("patch", f"/api/v1/customers/{customer_id}", {"display_name": "Changed"}),
        ("delete", f"/api/v1/customers/{customer_id}", None),
    ]
    for method, path, body in calls:
        response = getattr(client_db, method)(
            path, headers=member, **({"json": body} if body else {})
        )
        _assert_forbidden(response)
        for value in PII.values():
            assert value not in response.text
    assert (_customers(workspace_id), _snapshot(workspace_id)) == before

    # guest.read allows reading but never writing.
    _grant(client_db, owner_token, workspace_id, membership_id, ["guest.read"])
    listing = client_db.get("/api/v1/customers", headers=member)
    assert listing.status_code == 200, listing.text
    assert [item["id"] for item in listing.json()["data"]["items"]] == [customer_id]
    detail = client_db.get(f"/api/v1/customers/{customer_id}", headers=member)
    assert detail.status_code == 200
    assert detail.json()["data"]["email"] == PII["email"]
    granted = (_customers(workspace_id), _snapshot(workspace_id))
    for method, path, body in calls[2:]:
        _assert_forbidden(
            getattr(client_db, method)(
                path, headers=member, **({"json": body} if body else {})
            )
        )
    assert (_customers(workspace_id), _snapshot(workspace_id)) == granted
    assert [event.action for event in _customer_audit(workspace_id)] == [
        "CUSTOMER_CREATED"
    ]


def test_f2_owner_writes_are_audited_without_pii(client_db):
    owner, owner_token = _owner(client_db, "f2-audit@access.example")
    workspace_id = owner["workspace"]["id"]
    headers = _headers(owner_token)
    created = client_db.post("/api/v1/customers", headers=headers, json=PII)
    assert created.status_code == 201
    customer_id = created.json()["data"]["id"]
    updated = client_db.patch(
        f"/api/v1/customers/{customer_id}",
        headers=headers,
        json={"phone": "+66811111111"},
    )
    assert updated.status_code == 200
    deleted = client_db.delete(f"/api/v1/customers/{customer_id}", headers=headers)
    assert deleted.status_code == 200

    events = _customer_audit(workspace_id)
    assert [event.action for event in events] == [
        "CUSTOMER_CREATED",
        "CUSTOMER_UPDATED",
        "CUSTOMER_DELETED",
    ]
    assert all(str(event.resource_id) == customer_id for event in events)
    assert all(event.area == "GUESTS" for event in events)
    assert events[1].safe_metadata == {"changed_fields": ["phone"]}
    serialized = repr([event.safe_metadata for event in events])
    for value in (*PII.values(), "+66811111111"):
        assert value not in serialized


def test_f2_customer_ids_from_another_workspace_do_not_leak(client_db):
    owner_a, token_a = _owner(client_db, "f2-a@access.example")
    owner_b, token_b = _owner(client_db, "f2-b@access.example")
    created = client_db.post("/api/v1/customers", headers=_headers(token_a), json=PII)
    customer_id = created.json()["data"]["id"]
    before = _customers(owner_a["workspace"]["id"])
    headers_b = _headers(token_b)
    for method, body in (
        ("get", None),
        ("patch", {"display_name": "X"}),
        ("delete", None),
    ):
        response = getattr(client_db, method)(
            f"/api/v1/customers/{customer_id}",
            headers=headers_b,
            **({"json": body} if body else {}),
        )
        assert response.status_code == 404, response.text
        for value in PII.values():
            assert value not in response.text
    listing = client_db.get("/api/v1/customers", headers=headers_b).json()["data"]
    assert listing["items"] == []
    # A membership-less header for Workspace A is rejected before any query.
    forged = client_db.get(
        "/api/v1/customers", headers=_headers(token_b, owner_a["workspace"]["id"])
    )
    _assert_forbidden(forged)
    assert _customers(owner_a["workspace"]["id"]) == before
    assert len(_customer_audit(owner_b["workspace"]["id"])) == 0


# ------------------------------------------------------------------- F3


def _payment_state(payment_id: str):
    async def read():
        async with TestSessionLocal() as session:
            item = await session.get(Payment, uuid.UUID(payment_id))
            return (
                item.status,
                item.booking_application_status,
                item.booking_reviewed_at,
                item.booking_review_note,
            )

    return asyncio.run(read())


def test_f3_payment_exceptions_require_payment_read(client_db):
    owner, owner_token, _, _, payment_id = _scenario(client_db)
    workspace_id = owner["workspace"]["id"]
    _mark_payment_verified(payment_id, amount=Decimal("1.00"))
    assert _retry(client_db, owner_token, payment_id).status_code == 200
    assert [
        row["payment_id"] for row in _exceptions(client_db, owner_token).json()["data"]
    ] == [payment_id]

    user, token = _zero_workspace_account(client_db, "f3-member@access.example")
    membership_id = _add_member(workspace_id, user["id"], WorkspaceRole.MEMBER)
    member = _headers(token, workspace_id)
    before = (_payment_state(payment_id), _snapshot(workspace_id))
    denied = client_db.get("/api/v1/hotel/payment-exceptions", headers=member)
    _assert_forbidden(denied)
    assert payment_id not in denied.text
    assert (_payment_state(payment_id), _snapshot(workspace_id)) == before

    _grant(client_db, owner_token, workspace_id, membership_id, ["payment.read"])
    allowed = client_db.get("/api/v1/hotel/payment-exceptions", headers=member)
    assert allowed.status_code == 200, allowed.text
    assert [row["payment_id"] for row in allowed.json()["data"]] == [payment_id]
    # Resolution authority is unchanged: payment.read cannot reconcile.
    assert (
        client_db.post(
            f"/api/v1/hotel/payment-exceptions/{payment_id}/reconcile",
            headers=member,
        ).status_code
        == 403
    )

    # Another Workspace sees nothing, and cannot target this Workspace.
    _, other_token = _owner(client_db, "f3-other@access.example")
    assert _exceptions(client_db, other_token).json()["data"] == []
    _assert_forbidden(
        client_db.get(
            "/api/v1/hotel/payment-exceptions",
            headers=_headers(other_token, workspace_id),
        )
    )
    assert _payment_state(payment_id) == before[0]


def test_f2_guest_manage_is_required_for_customer_writes(client_db):
    owner, owner_token = _owner(client_db, "f2-manage@access.example")
    workspace_id = owner["workspace"]["id"]
    created = client_db.post(
        "/api/v1/customers", headers=_headers(owner_token), json=PII
    )
    customer_id = created.json()["data"]["id"]
    user, token = _zero_workspace_account(client_db, "f2-manager@access.example")
    membership_id = _add_member(workspace_id, user["id"], WorkspaceRole.MEMBER)
    member = _headers(token, workspace_id)
    writes = [
        ("post", "/api/v1/customers", {"display_name": "Walk-in"}),
        ("patch", f"/api/v1/customers/{customer_id}", {"display_name": "Renamed"}),
    ]

    # guest.manage alone is not enough: write responses return guest data,
    # so writers must also hold guest.read.
    _grant(client_db, owner_token, workspace_id, membership_id, ["guest.manage"])
    before = (_customers(workspace_id), _snapshot(workspace_id))
    for method, path, body in writes:
        _assert_forbidden(getattr(client_db, method)(path, headers=member, json=body))
    _assert_forbidden(
        client_db.delete(f"/api/v1/customers/{customer_id}", headers=member)
    )
    _assert_forbidden(client_db.get("/api/v1/customers", headers=member))
    assert (_customers(workspace_id), _snapshot(workspace_id)) == before

    _grant(
        client_db,
        owner_token,
        workspace_id,
        membership_id,
        ["guest.read", "guest.manage"],
    )
    made = client_db.post("/api/v1/customers", headers=member, json=writes[0][2])
    assert made.status_code == 201, made.text
    renamed = client_db.patch(writes[1][1], headers=member, json=writes[1][2])
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["display_name"] == "Renamed"
    removed = client_db.delete(f"/api/v1/customers/{customer_id}", headers=member)
    assert removed.status_code == 200, removed.text

    events = _customer_audit(workspace_id)
    assert [event.action for event in events] == [
        "CUSTOMER_CREATED",
        "CUSTOMER_CREATED",
        "CUSTOMER_UPDATED",
        "CUSTOMER_DELETED",
    ]
    assert {str(event.actor_user_id) for event in events[1:]} == {user["id"]}
    serialized = repr([event.safe_metadata for event in events])
    for value in (*PII.values(), "Walk-in", "Renamed"):
        assert value not in serialized


def test_f2_guest_manage_is_in_registry_and_owner_baseline(client_db):
    owner, owner_token = _owner(client_db, "f2-registry@access.example")
    registry = client_db.get(
        "/api/v1/workspaces/capabilities", headers=_headers(owner_token)
    ).json()["data"]["capabilities"]
    assert "guest.manage" in registry
    access = client_db.get(
        "/api/v1/workspaces/current/access", headers=_headers(owner_token)
    ).json()["data"]
    assert "guest.manage" in access["capabilities"]
    del owner
