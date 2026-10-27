"""Account billing and subscription-gated Workspace provisioning tests."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.billing import (
    BillingAccount,
    BillingAuditEvent,
    SubscriptionWorkspaceAllocation,
    WorkspaceSubscription,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.entitlement import EntitlementService
from app.services.workspace import WorkspaceService
from tests.conftest import TestSessionLocal


def _register(client: TestClient, email: str) -> tuple[dict, dict[str, str]]:
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret123", "full_name": email},
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
        "/api/v1/auth/login",
        json={"email": email, "password": "supersecret123"},
    )
    assert login.status_code == 200
    return registered.json()["data"], {
        "Authorization": f"Bearer {login.json()['data']['access_token']}"
    }


def _make_platform_admin(user_id: str) -> None:
    async def update() -> None:
        async with TestSessionLocal() as session:
            user = await session.get(User, uuid.UUID(user_id))
            user.is_platform_admin = True
            await session.commit()

    asyncio.run(update())


def _pending(client: TestClient, headers: dict[str, str]) -> dict:
    plans = client.get("/api/v1/billing/plans", headers=headers)
    assert plans.status_code == 200
    plan = plans.json()["data"][0]
    created = client.post(
        "/api/v1/billing/subscriptions",
        headers=headers,
        json={"plan_id": plan["id"]},
    )
    assert created.status_code == 201
    return created.json()["data"]


def _activate(
    client: TestClient,
    subscription_id: str,
    headers: dict[str, str],
    status: str = "ACTIVE",
):
    return client.post(
        f"/api/v1/platform/billing/subscriptions/{subscription_id}/activate",
        headers=headers,
        json={"status": status, "reason": "Pilot owner approval"},
    )


def test_zero_workspace_user_can_view_plans_and_create_pending_subscription(
    client_db: TestClient,
) -> None:
    user, headers = _register(client_db, "billing-zero@example.com")
    assert client_db.get("/api/v1/workspaces", headers=headers).json()["data"] == []

    pending = _pending(client_db, headers)
    assert pending["workspace_id"] is None
    assert pending["status"] == "PENDING_ACTIVATION"
    assert pending["workspace_limit"] == 1
    assert pending["allocated_workspaces"] == 0

    duplicate = _pending(client_db, headers)
    assert duplicate["id"] == pending["id"]
    account = client_db.get("/api/v1/billing/account", headers=headers).json()[
        "data"
    ]
    assert account["owner_user_id"] == user["user"]["id"]
    assert len(account["subscriptions"]) == 1

    async def inspect() -> None:
        async with TestSessionLocal() as session:
            assert await session.scalar(select(func.count(BillingAccount.id))) == 1
            actions = list(
                await session.scalars(
                    select(BillingAuditEvent.action).order_by(
                        BillingAuditEvent.created_at
                    )
                )
            )
            assert actions == ["BILLING_ACCOUNT_CREATED", "SUBSCRIPTION_CREATED"]

    asyncio.run(inspect())


def test_manual_activation_is_platform_only_and_idempotent(
    client_db: TestClient,
) -> None:
    owner, owner_headers = _register(client_db, "pilot-owner@example.com")
    admin, admin_headers = _register(client_db, "platform-admin@example.com")
    pending = _pending(client_db, owner_headers)

    forbidden = _activate(client_db, pending["id"], owner_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"

    other_forbidden = _activate(client_db, pending["id"], admin_headers)
    assert other_forbidden.status_code == 403
    _make_platform_admin(admin["user"]["id"])

    activated = _activate(client_db, pending["id"], admin_headers)
    repeated = _activate(client_db, pending["id"], admin_headers)
    assert activated.status_code == repeated.status_code == 200
    assert activated.json()["data"]["status"] == "ACTIVE"

    async def inspect() -> None:
        async with TestSessionLocal() as session:
            events = await session.scalar(
                select(func.count(BillingAuditEvent.id)).where(
                    BillingAuditEvent.action == "SUBSCRIPTION_ACTIVATED",
                    BillingAuditEvent.subscription_id == uuid.UUID(pending["id"]),
                )
            )
            assert events == 1
            event = await session.scalar(
                select(BillingAuditEvent).where(
                    BillingAuditEvent.action == "SUBSCRIPTION_ACTIVATED"
                )
            )
            assert event.actor_user_id == uuid.UUID(admin["user"]["id"])
            assert event.old_status == "PENDING_ACTIVATION"
            assert event.new_status == "ACTIVE"

    asyncio.run(inspect())


@pytest.mark.parametrize("eligible_status", ["ACTIVE", "TRIALING"])
def test_eligible_subscription_provisions_exactly_one_workspace_atomically(
    client_db: TestClient, eligible_status: str
) -> None:
    owner, headers = _register(
        client_db, f"provision-{eligible_status.lower()}@example.com"
    )
    admin, admin_headers = _register(
        client_db, f"admin-{eligible_status.lower()}@example.com"
    )
    pending = _pending(client_db, headers)
    blocked = client_db.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Blocked Hotel", "subscription_id": pending["id"]},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "SUBSCRIPTION_NOT_ELIGIBLE"

    _make_platform_admin(admin["user"]["id"])
    assert _activate(
        client_db, pending["id"], admin_headers, eligible_status
    ).status_code == 200
    created = client_db.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Pilot Hotel", "subscription_id": pending["id"]},
    )
    assert created.status_code == 201
    workspace = created.json()["data"]
    assert workspace["owner_id"] == owner["user"]["id"]

    repeated = client_db.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Second Hotel", "subscription_id": pending["id"]},
    )
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "SUBSCRIPTION_ALLOCATION_EXHAUSTED"

    async def inspect() -> None:
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == uuid.UUID(workspace["id"])
                )
            )
            assert membership.role == WorkspaceRole.OWNER
            allocation = await session.scalar(
                select(SubscriptionWorkspaceAllocation).where(
                    SubscriptionWorkspaceAllocation.subscription_id
                    == uuid.UUID(pending["id"])
                )
            )
            assert str(allocation.workspace_id) == workspace["id"]
            subscription = await EntitlementService(session).current_subscription(
                uuid.UUID(workspace["id"])
            )
            assert subscription.id == uuid.UUID(pending["id"])
            assert await session.scalar(
                select(func.count(BillingAuditEvent.id)).where(
                    BillingAuditEvent.action == "WORKSPACE_PROVISIONED"
                )
            ) == 1

    asyncio.run(inspect())


def test_subscription_ownership_and_workspace_provisioning_are_isolated(
    client_db: TestClient,
) -> None:
    _, first_headers = _register(client_db, "billing-first-owner@example.com")
    _, second_headers = _register(client_db, "billing-second-owner@example.com")
    admin, admin_headers = _register(client_db, "billing-admin@example.com")
    pending = _pending(client_db, first_headers)
    _make_platform_admin(admin["user"]["id"])
    assert _activate(client_db, pending["id"], admin_headers).status_code == 200

    forged = client_db.post(
        "/api/v1/workspaces",
        headers=second_headers,
        json={"name": "Stolen Hotel", "subscription_id": pending["id"]},
    )
    assert forged.status_code == 403
    assert forged.json()["error"]["code"] == "BILLING_ACCOUNT_FORBIDDEN"


def test_failed_workspace_transaction_does_not_consume_allocation(
    client_db: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, headers = _register(client_db, "billing-rollback@example.com")
    admin, admin_headers = _register(client_db, "billing-rollback-admin@example.com")
    pending = _pending(client_db, headers)
    _make_platform_admin(admin["user"]["id"])
    assert _activate(client_db, pending["id"], admin_headers).status_code == 200

    async def fail_build(*args, **kwargs):
        raise RuntimeError("forced workspace build failure")

    monkeypatch.setattr(WorkspaceService, "build_with_owner", fail_build)
    with pytest.raises(RuntimeError, match="forced workspace build failure"):
        client_db.post(
            "/api/v1/workspaces",
            headers=headers,
            json={"name": "Rollback Hotel", "subscription_id": pending["id"]},
        )

    async def inspect() -> None:
        async with TestSessionLocal() as session:
            assert await session.scalar(select(func.count(Workspace.id))) == 0
            assert await session.scalar(
                select(func.count(SubscriptionWorkspaceAllocation.id))
            ) == 0
            subscription = await session.get(
                WorkspaceSubscription, uuid.UUID(pending["id"])
            )
            assert subscription.workspace_id is None

    asyncio.run(inspect())


def test_employee_membership_requires_no_owned_subscription(
    client_db: TestClient,
) -> None:
    owner, owner_headers = _register(client_db, "employer@example.com")
    employee, employee_headers = _register(client_db, "employee@example.com")
    admin, admin_headers = _register(client_db, "employee-admin@example.com")
    pending = _pending(client_db, owner_headers)
    _make_platform_admin(admin["user"]["id"])
    _activate(client_db, pending["id"], admin_headers)
    workspace = client_db.post(
        "/api/v1/workspaces",
        headers=owner_headers,
        json={"name": "Employer Hotel", "subscription_id": pending["id"]},
    ).json()["data"]

    async def add_employee() -> None:
        async with TestSessionLocal() as session:
            session.add(
                WorkspaceMember(
                    workspace_id=uuid.UUID(workspace["id"]),
                    user_id=uuid.UUID(employee["user"]["id"]),
                    role=WorkspaceRole.MEMBER,
                )
            )
            await session.commit()

    asyncio.run(add_employee())
    memberships = client_db.get("/api/v1/workspaces", headers=employee_headers)
    assert memberships.status_code == 200
    assert [item["id"] for item in memberships.json()["data"]] == [workspace["id"]]
    assert client_db.get(
        "/api/v1/billing/account", headers=employee_headers
    ).json()["data"] is None


def test_user_can_own_one_workspace_and_work_in_another(
    client_db: TestClient,
) -> None:
    owner_a, headers_a = _register(client_db, "multi-owner-a@example.com")
    owner_b, headers_b = _register(client_db, "multi-owner-b@example.com")
    admin, admin_headers = _register(client_db, "multi-platform-admin@example.com")
    _make_platform_admin(admin["user"]["id"])

    pending_a = _pending(client_db, headers_a)
    pending_b = _pending(client_db, headers_b)
    assert _activate(client_db, pending_a["id"], admin_headers).status_code == 200
    assert _activate(client_db, pending_b["id"], admin_headers).status_code == 200
    workspace_a = client_db.post(
        "/api/v1/workspaces",
        headers=headers_a,
        json={"name": "Owned Hotel A", "subscription_id": pending_a["id"]},
    ).json()["data"]
    workspace_b = client_db.post(
        "/api/v1/workspaces",
        headers=headers_b,
        json={"name": "Employer Hotel B", "subscription_id": pending_b["id"]},
    ).json()["data"]

    async def add_membership() -> None:
        async with TestSessionLocal() as session:
            session.add(
                WorkspaceMember(
                    workspace_id=uuid.UUID(workspace_b["id"]),
                    user_id=uuid.UUID(owner_a["user"]["id"]),
                    role=WorkspaceRole.MEMBER,
                )
            )
            await session.commit()

    asyncio.run(add_membership())
    memberships = client_db.get("/api/v1/workspaces", headers=headers_a)
    assert memberships.status_code == 200
    assert {item["id"] for item in memberships.json()["data"]} == {
        workspace_a["id"],
        workspace_b["id"],
    }
    account = client_db.get("/api/v1/billing/account", headers=headers_a)
    assert account.status_code == 200
    assert [item["id"] for item in account.json()["data"]["subscriptions"]] == [
        pending_a["id"]
    ]
