"""Direct PostgreSQL coverage for Workspace access and granular capabilities."""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.audit import WorkspaceAuditEvent
from app.models.workspace_access import (
    WorkspaceAccessAuditEvent,
    WorkspaceAccessRequest,
    WorkspaceAccessRequestStatus,
    WorkspaceJoinSetting,
    WorkspaceMemberCapability,
)
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from tests.conftest import TestSessionLocal, register_verify_and_login


def _headers(token: str, workspace_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        headers["X-Workspace-ID"] = workspace_id
    return headers


def _zero_workspace_account(client: TestClient, email: str) -> tuple[dict, str]:
    password = "supersecret123"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Employee"},
    )
    assert registered.status_code == 201
    verified = client.post(
        "/api/v1/auth/verify-email",
        json={
            "email": email,
            "otp": client.app.state.fake_email_provider.latest_otp,
        },
    )
    assert verified.status_code == 200
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    return registered.json()["data"]["user"], login.json()["data"]["access_token"]


def _owner(client: TestClient, email: str = "owner@access.example"):
    data, token = register_verify_and_login(client, email=email)
    return data, token


def _join_code(client: TestClient, owner: dict, token: str) -> str:
    response = client.post(
        f"/api/v1/workspaces/{owner['workspace']['id']}/join-code/regenerate",
        headers=_headers(token),
    )
    assert response.status_code == 200
    return response.json()["data"]["join_code"]


def _request(client: TestClient, token: str, code: str, message: str = "Join"):
    return client.post(
        "/api/v1/workspace-access/requests",
        headers=_headers(token),
        json={"code": code, "message": message},
    )


def _add_member(workspace_id: str, user_id: str, role: WorkspaceRole) -> str:
    async def insert() -> str:
        async with TestSessionLocal() as session:
            member = WorkspaceMember(
                workspace_id=uuid.UUID(workspace_id),
                user_id=uuid.UUID(user_id),
                role=role,
            )
            session.add(member)
            await session.commit()
            return str(member.id)

    return asyncio.run(insert())


def test_join_code_resolves_minimal_identity_and_is_hashed(client_db: TestClient):
    owner, token = _owner(client_db)
    code = _join_code(client_db, owner, token)

    response = client_db.post(
        "/api/v1/workspace-access/resolve-code",
        headers=_headers(token),
        json={"code": code.lower()},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"name": owner["workspace"]["name"]}

    async def inspect():
        async with TestSessionLocal() as session:
            setting = await session.scalar(select(WorkspaceJoinSetting))
            assert setting is not None
            assert setting.join_code_hash != code
            assert code.replace("-", "") not in setting.join_code_hash
            assert len(setting.join_code_hash or "") == 64

    asyncio.run(inspect())


def test_invalid_disabled_and_stale_join_codes_fail_closed(client_db: TestClient):
    owner, token = _owner(client_db)
    first = _join_code(client_db, owner, token)
    second = _join_code(client_db, owner, token)
    invalid = client_db.post(
        "/api/v1/workspace-access/resolve-code",
        headers=_headers(token),
        json={"code": first},
    )
    assert invalid.status_code == 404
    assert invalid.json()["error"]["code"] == "WORKSPACE_JOIN_CODE_INVALID"

    disabled = client_db.patch(
        f"/api/v1/workspaces/{owner['workspace']['id']}/join-settings",
        headers=_headers(token),
        json={"join_enabled": False},
    )
    assert disabled.status_code == 200
    unavailable = client_db.post(
        "/api/v1/workspace-access/resolve-code",
        headers=_headers(token),
        json={"code": second},
    )
    assert unavailable.status_code == 404
    assert "workspace_id" not in unavailable.text


def test_request_is_idempotent_and_does_not_create_membership(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    user, token = _zero_workspace_account(client_db, "employee@access.example")
    code = _join_code(client_db, owner, owner_token)

    first = _request(client_db, token, code)
    second = _request(client_db, token, code)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert first.json()["data"]["status"] == "PENDING"

    async def inspect():
        async with TestSessionLocal() as session:
            requests = list(await session.scalars(select(WorkspaceAccessRequest)))
            memberships = list(
                await session.scalars(
                    select(WorkspaceMember).where(
                        WorkspaceMember.user_id == uuid.UUID(user["id"]),
                        WorkspaceMember.workspace_id
                        == uuid.UUID(owner["workspace"]["id"]),
                    )
                )
            )
            assert len(requests) == 1
            assert memberships == []

    asyncio.run(inspect())


def test_user_can_cancel_only_pending_request(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    _, token = _zero_workspace_account(client_db, "cancel@access.example")
    request = _request(client_db, token, _join_code(client_db, owner, owner_token))
    request_id = request.json()["data"]["id"]
    cancelled = client_db.post(
        f"/api/v1/workspace-access/requests/{request_id}/cancel",
        headers=_headers(token),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    again = client_db.post(
        f"/api/v1/workspace-access/requests/{request_id}/cancel",
        headers=_headers(token),
    )
    assert again.status_code == 409


def test_owner_approval_atomically_creates_member_and_grants(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    user, token = _zero_workspace_account(client_db, "approved@access.example")
    requested = _request(
        client_db, token, _join_code(client_db, owner, owner_token), "Front desk"
    )
    request_id = requested.json()["data"]["id"]
    approved = client_db.post(
        f"/api/v1/workspaces/{owner['workspace']['id']}/access-requests/"
        f"{request_id}/approve",
        headers=_headers(owner_token),
        json={
            "role": "member",
            "capabilities": ["conversation.read", "booking.read"],
        },
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["user_id"] == user["id"]
    assert set(approved.json()["data"]["capabilities"]) == {
        "dashboard.view",
        "conversation.read",
        "booking.read",
    }

    async def inspect():
        async with TestSessionLocal() as session:
            item = await session.get(WorkspaceAccessRequest, uuid.UUID(request_id))
            grants = list(
                await session.scalars(
                    select(WorkspaceMemberCapability).where(
                        WorkspaceMemberCapability.workspace_id
                        == uuid.UUID(owner["workspace"]["id"])
                    )
                )
            )
            assert item and item.status is WorkspaceAccessRequestStatus.APPROVED
            assert len(grants) == 2
            global_actions = set(
                await session.scalars(
                    select(WorkspaceAuditEvent.action).where(
                        WorkspaceAuditEvent.workspace_id
                        == uuid.UUID(owner["workspace"]["id"])
                    )
                )
            )
            assert {
                "WORKSPACE_ACCESS_REQUESTED",
                "WORKSPACE_ACCESS_APPROVED",
            } <= global_actions

    asyncio.run(inspect())


def test_repeated_approval_and_cross_workspace_review_are_rejected(client_db):
    owner_a, token_a = _owner(client_db, "a@access.example")
    owner_b, token_b = _owner(client_db, "b@access.example")
    _, employee_token = _zero_workspace_account(client_db, "cross@access.example")
    item = _request(
        client_db, employee_token, _join_code(client_db, owner_a, token_a)
    ).json()["data"]
    wrong = client_db.post(
        f"/api/v1/workspaces/{owner_b['workspace']['id']}/access-requests/"
        f"{item['id']}/approve",
        headers=_headers(token_b),
        json={"role": "member", "capabilities": []},
    )
    assert wrong.status_code == 404
    path = (
        f"/api/v1/workspaces/{owner_a['workspace']['id']}/access-requests/"
        f"{item['id']}/approve"
    )
    assert (
        client_db.post(
            path,
            headers=_headers(token_a),
            json={"role": "member", "capabilities": []},
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            path,
            headers=_headers(token_a),
            json={"role": "member", "capabilities": []},
        ).status_code
        == 409
    )


def test_admin_can_approve_member_but_not_admin(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    admin, admin_token = _zero_workspace_account(client_db, "admin@access.example")
    _add_member(owner["workspace"]["id"], admin["id"], WorkspaceRole.ADMIN)
    _, employee_token = _zero_workspace_account(client_db, "worker@access.example")
    item = _request(
        client_db, employee_token, _join_code(client_db, owner, owner_token)
    ).json()["data"]
    url = (
        f"/api/v1/workspaces/{owner['workspace']['id']}/access-requests/"
        f"{item['id']}/approve"
    )
    denied = client_db.post(
        url,
        headers=_headers(admin_token),
        json={"role": "admin", "capabilities": []},
    )
    assert denied.status_code == 403
    allowed = client_db.post(
        url,
        headers=_headers(admin_token),
        json={"role": "member", "capabilities": ["room.read"]},
    )
    assert allowed.status_code == 200


def test_member_cannot_review_or_self_grant(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    member, member_token = _zero_workspace_account(client_db, "member@access.example")
    membership_id = _add_member(
        owner["workspace"]["id"], member["id"], WorkspaceRole.MEMBER
    )
    _, applicant_token = _zero_workspace_account(client_db, "applicant@access.example")
    item = _request(
        client_db, applicant_token, _join_code(client_db, owner, owner_token)
    ).json()["data"]
    review = client_db.post(
        f"/api/v1/workspaces/{owner['workspace']['id']}/access-requests/"
        f"{item['id']}/approve",
        headers=_headers(member_token),
        json={"role": "member", "capabilities": []},
    )
    assert review.status_code == 403
    self_grant = client_db.put(
        f"/api/v1/workspaces/{owner['workspace']['id']}/members/"
        f"{membership_id}/capabilities",
        headers=_headers(member_token),
        json={"capabilities": ["workspace.members.manage"]},
    )
    assert self_grant.status_code == 403


def test_capability_grant_revoke_and_effective_access_are_authoritative(client_db):
    owner, owner_token = _owner(client_db)
    member, member_token = _zero_workspace_account(client_db, "caps@access.example")
    membership_id = _add_member(
        owner["workspace"]["id"], member["id"], WorkspaceRole.MEMBER
    )
    url = (
        f"/api/v1/workspaces/{owner['workspace']['id']}/members/"
        f"{membership_id}/capabilities"
    )
    granted = client_db.put(
        url,
        headers=_headers(owner_token),
        json={"capabilities": ["automation.read", "pms.read"]},
    )
    assert granted.status_code == 200
    access = client_db.get(
        "/api/v1/workspaces/current/access",
        params={"workspace_id": owner["workspace"]["id"]},
        headers=_headers(member_token),
    )
    assert set(access.json()["data"]["capabilities"]) == {
        "dashboard.view",
        "automation.read",
        "pms.read",
    }
    revoked = client_db.put(
        url, headers=_headers(owner_token), json={"capabilities": []}
    )
    assert revoked.status_code == 200
    refreshed = client_db.get(
        "/api/v1/workspaces/current/access",
        params={"workspace_id": owner["workspace"]["id"]},
        headers=_headers(member_token),
    )
    assert refreshed.json()["data"]["capabilities"] == ["dashboard.view"]

    async def global_audit_count():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(func.count())
                .select_from(WorkspaceAuditEvent)
                .where(
                    WorkspaceAuditEvent.workspace_id
                    == uuid.UUID(owner["workspace"]["id"]),
                    WorkspaceAuditEvent.action == "MEMBER_CAPABILITIES_CHANGED",
                    WorkspaceAuditEvent.resource_id == uuid.UUID(membership_id),
                )
            )

    assert asyncio.run(global_audit_count()) == 2


def test_invalid_and_cross_workspace_capability_changes_fail(client_db):
    owner_a, token_a = _owner(client_db, "grant-a@access.example")
    owner_b, token_b = _owner(client_db, "grant-b@access.example")
    member, _ = _zero_workspace_account(client_db, "grant-user@access.example")
    membership_id = _add_member(
        owner_a["workspace"]["id"], member["id"], WorkspaceRole.MEMBER
    )
    invalid = client_db.put(
        f"/api/v1/workspaces/{owner_a['workspace']['id']}/members/"
        f"{membership_id}/capabilities",
        headers=_headers(token_a),
        json={"capabilities": ["platform.admin"]},
    )
    assert invalid.status_code == 403
    cross = client_db.put(
        f"/api/v1/workspaces/{owner_b['workspace']['id']}/members/"
        f"{membership_id}/capabilities",
        headers=_headers(token_b),
        json={"capabilities": ["booking.read"]},
    )
    assert cross.status_code == 404


def test_owner_is_immutable_and_retains_all_capabilities(client_db):
    owner, token = _owner(client_db)
    members = client_db.get(
        f"/api/v1/workspaces/{owner['workspace']['id']}/members",
        headers=_headers(token),
    ).json()["data"]
    owner_member = members[0]
    assert "workspace.members.manage" in owner_member["capabilities"]
    downgrade = client_db.patch(
        f"/api/v1/workspaces/{owner['workspace']['id']}/members/{owner_member['id']}",
        headers=_headers(token),
        json={"role": "member"},
    )
    assert downgrade.status_code == 403
    remove = client_db.delete(
        f"/api/v1/workspaces/{owner['workspace']['id']}/members/{owner_member['id']}",
        headers=_headers(token),
    )
    assert remove.status_code == 403


def test_multi_workspace_capabilities_and_context_header_are_isolated(client_db):
    owner_a, token_a = _owner(client_db, "multi-a@access.example")
    owner_b, token_b = _owner(client_db, "multi-b@access.example")
    user, user_token = _zero_workspace_account(client_db, "multi@access.example")
    member_a = _add_member(owner_a["workspace"]["id"], user["id"], WorkspaceRole.MEMBER)
    member_b = _add_member(owner_b["workspace"]["id"], user["id"], WorkspaceRole.MEMBER)
    for owner, token, member_id, capability in (
        (owner_a, token_a, member_a, "automation.read"),
        (owner_b, token_b, member_b, "pms.read"),
    ):
        response = client_db.put(
            f"/api/v1/workspaces/{owner['workspace']['id']}/members/"
            f"{member_id}/capabilities",
            headers=_headers(token),
            json={"capabilities": [capability]},
        )
        assert response.status_code == 200

    a = client_db.get(
        "/api/v1/workspaces/current/access",
        params={"workspace_id": owner_a["workspace"]["id"]},
        headers=_headers(user_token),
    ).json()["data"]
    b = client_db.get(
        "/api/v1/workspaces/current/access",
        params={"workspace_id": owner_b["workspace"]["id"]},
        headers=_headers(user_token),
    ).json()["data"]
    assert "automation.read" in a["capabilities"]
    assert "pms.read" not in a["capabilities"]
    assert "pms.read" in b["capabilities"]
    assert "automation.read" not in b["capabilities"]

    selected = client_db.get(
        "/api/v1/automations",
        headers=_headers(user_token, owner_a["workspace"]["id"]),
    )
    assert selected.status_code == 200
    wrong_permission = client_db.get(
        "/api/v1/automations",
        headers=_headers(user_token, owner_b["workspace"]["id"]),
    )
    assert wrong_permission.status_code == 403


def test_request_rejection_and_audit_are_safe(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    _, token = _zero_workspace_account(client_db, "reject@access.example")
    code = _join_code(client_db, owner, owner_token)
    item = _request(client_db, token, code).json()["data"]
    rejected = client_db.post(
        f"/api/v1/workspaces/{owner['workspace']['id']}/access-requests/"
        f"{item['id']}/reject",
        headers=_headers(owner_token),
        json={"reason": "No opening"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "REJECTED"

    async def inspect():
        async with TestSessionLocal() as session:
            events = list(await session.scalars(select(WorkspaceAccessAuditEvent)))
            assert any(e.action == "WORKSPACE_ACCESS_REQUESTED" for e in events)
            assert any(e.action == "WORKSPACE_ACCESS_REJECTED" for e in events)
            assert all(code not in str(event.summary) for event in events)

    asyncio.run(inspect())


def test_join_code_lookup_is_rate_limited(client_db: TestClient):
    owner, token = _owner(client_db)
    code = _join_code(client_db, owner, token)
    statuses = []
    for _ in range(11):
        response = client_db.post(
            "/api/v1/workspace-access/resolve-code",
            headers=_headers(token),
            json={"code": code},
        )
        statuses.append(response.status_code)
    assert statuses[:10] == [200] * 10
    assert statuses[-1] == 429


def test_direct_operational_apis_require_explicit_member_capabilities(client_db):
    owner, owner_token = _owner(client_db)
    member, member_token = _zero_workspace_account(
        client_db, "direct-api@access.example"
    )
    membership_id = _add_member(
        owner["workspace"]["id"], member["id"], WorkspaceRole.MEMBER
    )
    member_headers = _headers(member_token, owner["workspace"]["id"])
    checks = {
        "/api/v1/conversations": "conversation.read",
        "/api/v1/crm/customers": "guest.read",
        "/api/v1/payments": "payment.read",
        "/api/v1/knowledge": "knowledge.read",
        "/api/v1/hotel/bookings": "booking.read",
        "/api/v1/hotel/housekeeping/tasks": "housekeeping.read",
        "/api/v1/automations": "automation.read",
    }

    for path in checks:
        denied = client_db.get(path, headers=member_headers)
        assert denied.status_code == 403, path

    granted = client_db.put(
        f"/api/v1/workspaces/{owner['workspace']['id']}/members/"
        f"{membership_id}/capabilities",
        headers=_headers(owner_token),
        json={"capabilities": list(checks.values())},
    )
    assert granted.status_code == 200

    for path in checks:
        allowed = client_db.get(path, headers=member_headers)
        assert allowed.status_code == 200, path


# --------------------------------------------- F1: role escalation boundaries


def _access_snapshot(workspace_id: str) -> dict:
    """Everything a denied membership request must leave untouched."""

    async def read() -> dict:
        async with TestSessionLocal() as session:
            scope = uuid.UUID(workspace_id)
            members = {
                str(item.id): item.role.value
                for item in await session.scalars(
                    select(WorkspaceMember).where(WorkspaceMember.workspace_id == scope)
                )
            }
            grants = sorted(
                (str(item.membership_id), item.capability)
                for item in await session.scalars(
                    select(WorkspaceMemberCapability).where(
                        WorkspaceMemberCapability.workspace_id == scope
                    )
                )
            )
            requests = {
                str(item.id): item.status.value
                for item in await session.scalars(
                    select(WorkspaceAccessRequest).where(
                        WorkspaceAccessRequest.workspace_id == scope
                    )
                )
            }
            audits = await session.scalar(
                select(func.count())
                .select_from(WorkspaceAuditEvent)
                .where(WorkspaceAuditEvent.workspace_id == scope)
            )
            access_audits = await session.scalar(
                select(func.count())
                .select_from(WorkspaceAccessAuditEvent)
                .where(WorkspaceAccessAuditEvent.workspace_id == scope)
            )
            return {
                "members": members,
                "grants": grants,
                "requests": requests,
                "audits": audits,
                "access_audits": access_audits,
            }

    return asyncio.run(read())


def _assert_forbidden(response, message_fragment: str) -> None:
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["error"]["code"] == "FORBIDDEN"
    assert message_fragment in body["message"]


def _member_manager(client: TestClient, owner: dict, owner_token: str):
    """A MEMBER delegated workspace.members.manage by the owner."""

    manager, manager_token = _zero_workspace_account(client, "manager@access.example")
    membership_id = _add_member(
        owner["workspace"]["id"], manager["id"], WorkspaceRole.MEMBER
    )
    granted = client.put(
        f"/api/v1/workspaces/{owner['workspace']['id']}/members/"
        f"{membership_id}/capabilities",
        headers=_headers(owner_token),
        json={"capabilities": ["workspace.members.manage", "room.read"]},
    )
    assert granted.status_code == 200, granted.text
    return manager, manager_token, membership_id


def test_member_manager_cannot_promote_member_to_admin(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    workspace_id = owner["workspace"]["id"]
    _, manager_token, _ = _member_manager(client_db, owner, owner_token)
    target, _ = _zero_workspace_account(client_db, "target@access.example")
    target_id = _add_member(workspace_id, target["id"], WorkspaceRole.MEMBER)
    before = _access_snapshot(workspace_id)

    response = client_db.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{target_id}",
        headers=_headers(manager_token),
        json={"role": "admin"},
    )

    _assert_forbidden(response, "Only workspace owners can grant admin access")
    assert _access_snapshot(workspace_id) == before

    # The delegated scope for ordinary members is preserved.
    kept = client_db.put(
        f"/api/v1/workspaces/{workspace_id}/members/{target_id}/capabilities",
        headers=_headers(manager_token),
        json={"capabilities": ["room.read"]},
    )
    assert kept.status_code == 200, kept.text


def test_member_manager_cannot_remove_or_demote_admin(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    workspace_id = owner["workspace"]["id"]
    _, manager_token, _ = _member_manager(client_db, owner, owner_token)
    admin, _ = _zero_workspace_account(client_db, "admin@access.example")
    admin_id = _add_member(workspace_id, admin["id"], WorkspaceRole.ADMIN)
    before = _access_snapshot(workspace_id)

    removed = client_db.delete(
        f"/api/v1/workspaces/{workspace_id}/members/{admin_id}",
        headers=_headers(manager_token),
    )
    _assert_forbidden(removed, "Only workspace owners can manage admins")
    demoted = client_db.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{admin_id}",
        headers=_headers(manager_token),
        json={"role": "member"},
    )
    _assert_forbidden(demoted, "Only workspace owners can manage admins")
    regranted = client_db.put(
        f"/api/v1/workspaces/{workspace_id}/members/{admin_id}/capabilities",
        headers=_headers(manager_token),
        json={"capabilities": []},
    )
    _assert_forbidden(regranted, "Only workspace owners can manage admins")
    assert _access_snapshot(workspace_id) == before


def test_member_manager_cannot_approve_account_as_admin(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    workspace_id = owner["workspace"]["id"]
    _, manager_token, _ = _member_manager(client_db, owner, owner_token)
    applicant, applicant_token = _zero_workspace_account(
        client_db, "applicant@access.example"
    )
    item = _request(
        client_db, applicant_token, _join_code(client_db, owner, owner_token)
    ).json()["data"]
    url = f"/api/v1/workspaces/{workspace_id}/access-requests/{item['id']}/approve"
    before = _access_snapshot(workspace_id)

    response = client_db.post(
        url, headers=_headers(manager_token), json={"role": "admin", "capabilities": []}
    )

    _assert_forbidden(response, "Only workspace owners can approve admin access")
    after = _access_snapshot(workspace_id)
    assert after == before
    assert after["requests"][item["id"]] == "PENDING"
    assert applicant["id"] not in str(after["members"])

    # Approving as an ordinary member with held capabilities still works.
    allowed = client_db.post(
        url,
        headers=_headers(manager_token),
        json={"role": "member", "capabilities": ["room.read"]},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["role"] == "member"


def test_admin_cannot_appoint_admin(client_db: TestClient):
    owner, _ = _owner(client_db)
    workspace_id = owner["workspace"]["id"]
    admin, admin_token = _zero_workspace_account(client_db, "admin@access.example")
    _add_member(workspace_id, admin["id"], WorkspaceRole.ADMIN)
    target, _ = _zero_workspace_account(client_db, "target@access.example")
    target_id = _add_member(workspace_id, target["id"], WorkspaceRole.MEMBER)
    before = _access_snapshot(workspace_id)

    response = client_db.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{target_id}",
        headers=_headers(admin_token),
        json={"role": "admin"},
    )

    _assert_forbidden(response, "Only workspace owners can grant admin access")
    assert _access_snapshot(workspace_id) == before


def test_owner_can_appoint_admin(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    workspace_id = owner["workspace"]["id"]
    target, _ = _zero_workspace_account(client_db, "target@access.example")
    target_id = _add_member(workspace_id, target["id"], WorkspaceRole.MEMBER)
    granted = client_db.put(
        f"/api/v1/workspaces/{workspace_id}/members/{target_id}/capabilities",
        headers=_headers(owner_token),
        json={"capabilities": ["room.read"]},
    )
    assert granted.status_code == 200
    before = _access_snapshot(workspace_id)

    response = client_db.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{target_id}",
        headers=_headers(owner_token),
        json={"role": "admin"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["role"] == "admin"
    after = _access_snapshot(workspace_id)
    assert after["members"][target_id] == "admin"
    # Admin authority comes from the role baseline; stale grants are removed.
    assert [grant for grant in after["grants"] if grant[0] == target_id] == []
    assert after["audits"] == before["audits"] + 1
    assert after["access_audits"] == before["access_audits"] + 1


def test_members_and_admins_cannot_change_their_own_role(client_db: TestClient):
    owner, owner_token = _owner(client_db)
    workspace_id = owner["workspace"]["id"]
    _, manager_token, manager_id = _member_manager(client_db, owner, owner_token)
    admin, admin_token = _zero_workspace_account(client_db, "admin@access.example")
    admin_id = _add_member(workspace_id, admin["id"], WorkspaceRole.ADMIN)
    before = _access_snapshot(workspace_id)

    for token, membership_id in ((manager_token, manager_id), (admin_token, admin_id)):
        response = client_db.patch(
            f"/api/v1/workspaces/{workspace_id}/members/{membership_id}",
            headers=_headers(token),
            json={"role": "admin"},
        )
        _assert_forbidden(response, "Cannot change your own workspace access")
    assert _access_snapshot(workspace_id) == before


def test_member_management_is_isolated_between_workspaces(client_db: TestClient):
    owner_a, token_a = _owner(client_db, "iso-a@access.example")
    owner_b, token_b = _owner(client_db, "iso-b@access.example")
    workspace_a = owner_a["workspace"]["id"]
    target, _ = _zero_workspace_account(client_db, "iso-target@access.example")
    target_id = _add_member(workspace_a, target["id"], WorkspaceRole.MEMBER)
    before = _access_snapshot(workspace_a)

    # Owner B addresses A's membership through B's own Workspace path.
    via_own = client_db.patch(
        f"/api/v1/workspaces/{owner_b['workspace']['id']}/members/{target_id}",
        headers=_headers(token_b),
        json={"role": "admin"},
    )
    assert via_own.status_code == 404
    # Owner B addresses A's Workspace directly without membership.
    direct = client_db.patch(
        f"/api/v1/workspaces/{workspace_a}/members/{target_id}",
        headers=_headers(token_b),
        json={"role": "admin"},
    )
    _assert_forbidden(direct, "Workspace membership required")
    removal = client_db.delete(
        f"/api/v1/workspaces/{workspace_a}/members/{target_id}",
        headers=_headers(token_b),
    )
    _assert_forbidden(removal, "Workspace membership required")
    assert _access_snapshot(workspace_a) == before
    del token_a
