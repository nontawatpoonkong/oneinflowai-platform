"""Direct authority, lifecycle, audit, and privacy tests for Platform Console."""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.audit import WorkspaceAuditEvent
from app.models.user import User
from tests.conftest import TestSessionLocal, provision_active_test_subscription


def _register(client: TestClient, email: str) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret123", "full_name": email},
    )
    assert response.status_code == 201
    user = response.json()["data"]["user"]
    assert user["is_platform_admin"] is False
    assert (
        client.post(
            "/api/v1/auth/verify-email",
            json={
                "email": email,
                "otp": client.app.state.fake_email_provider.latest_otp,
            },
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "supersecret123"},
    )
    return user, {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _platform_admin(client: TestClient, email: str = "platform@example.com"):
    user, headers = _register(client, email)

    async def update() -> None:
        async with TestSessionLocal() as session:
            item = await session.get(User, uuid.UUID(user["id"]))
            assert item is not None
            item.is_platform_admin = True
            await session.commit()

    asyncio.run(update())
    return user, headers


def _workspace(client: TestClient, user: dict, headers: dict[str, str], name: str):
    subscription_id = provision_active_test_subscription(user["id"])
    response = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": name, "subscription_id": subscription_id},
    )
    assert response.status_code == 201
    return response.json()["data"]


def _confirmed(reason: str = "Support investigation approved") -> dict:
    return {"reason": reason, "confirmed": True}


def test_only_platform_admin_can_access_cross_tenant_routes(
    client_db: TestClient,
) -> None:
    owner, owner_headers = _register(client_db, "owner-platform-denied@example.com")
    _workspace(client_db, owner, owner_headers, "Owner Hotel")
    denied = client_db.get("/api/v1/platform/users", headers=owner_headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"

    _, admin_headers = _platform_admin(client_db)
    accepted = client_db.get("/api/v1/platform/overview", headers=admin_headers)
    assert accepted.status_code == 200
    assert accepted.json()["data"]["metrics"]["total_users"] == 2


def test_user_suspend_reactivate_requires_reason_and_revokes_existing_session(
    client_db: TestClient,
) -> None:
    target, target_headers = _register(client_db, "suspend-me@example.com")
    _, admin_headers = _platform_admin(client_db)

    missing = client_db.post(
        f"/api/v1/platform/users/{target['id']}/suspend",
        headers=admin_headers,
        json={"reason": "", "confirmed": True},
    )
    assert missing.status_code == 422

    suspended = client_db.post(
        f"/api/v1/platform/users/{target['id']}/suspend",
        headers=admin_headers,
        json=_confirmed("Confirmed abuse investigation"),
    )
    assert suspended.status_code == 200
    assert suspended.json()["data"]["status"] == "SUSPENDED"
    assert client_db.get("/api/v1/auth/me", headers=target_headers).status_code == 403

    restored = client_db.post(
        f"/api/v1/platform/users/{target['id']}/reactivate",
        headers=admin_headers,
        json=_confirmed("Investigation resolved"),
    )
    assert restored.status_code == 200
    # Suspension revoked the session for good: reactivation does not revive
    # the old token, and a fresh login works.
    assert client_db.get("/api/v1/auth/me", headers=target_headers).status_code == 401
    login = client_db.post(
        "/api/v1/auth/login",
        json={"email": "suspend-me@example.com", "password": "supersecret123"},
    )
    fresh = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    assert client_db.get("/api/v1/auth/me", headers=fresh).status_code == 200

    audits = client_db.get(
        "/api/v1/platform/audit/events?action=PLATFORM_USER_SUSPENDED",
        headers=admin_headers,
    )
    assert audits.status_code == 200
    item = audits.json()["data"]["items"][0]
    assert item["actor_type"] == "PLATFORM_ADMIN"
    assert item["safe_metadata"]["reason"] == "Confirmed abuse investigation"


def test_workspace_suspension_blocks_operational_access_and_is_audited(
    client_db: TestClient,
) -> None:
    owner, owner_headers = _register(client_db, "hotel-owner@example.com")
    workspace = _workspace(client_db, owner, owner_headers, "Suspension Hotel")
    _, admin_headers = _platform_admin(client_db)

    suspended = client_db.post(
        f"/api/v1/platform/workspaces/{workspace['id']}/suspend",
        headers=admin_headers,
        json=_confirmed("Contract hold approved by operations"),
    )
    assert suspended.status_code == 200
    blocked = client_db.get(
        f"/api/v1/workspaces/current/access?workspace_id={workspace['id']}",
        headers=owner_headers,
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "WORKSPACE_SUSPENDED"
    instructions = client_db.get(
        f"/api/v1/workspaces/{workspace['id']}/ai-instructions",
        headers=owner_headers,
    )
    assert instructions.status_code == 403
    assert instructions.json()["error"]["code"] == "WORKSPACE_SUSPENDED"

    restored = client_db.post(
        f"/api/v1/platform/workspaces/{workspace['id']}/reactivate",
        headers=admin_headers,
        json=_confirmed("Contract hold cleared"),
    )
    assert restored.status_code == 200
    assert (
        client_db.get(
            f"/api/v1/workspaces/current/access?workspace_id={workspace['id']}",
            headers=owner_headers,
        ).status_code
        == 200
    )


def test_global_lists_are_bounded_and_safe(client_db: TestClient) -> None:
    _, admin_headers = _platform_admin(client_db)
    assert (
        client_db.get(
            "/api/v1/platform/users?page_size=101", headers=admin_headers
        ).status_code
        == 422
    )
    users = client_db.get("/api/v1/platform/users", headers=admin_headers)
    assert users.status_code == 200
    body = users.json()["data"]
    assert {"items", "page", "page_size", "total", "total_pages"} <= body.keys()
    serialized = users.text.lower()
    for secret_field in (
        "hashed_password",
        "credential_ciphertext",
        "confirmation_token_hash",
        "authorization",
    ):
        assert secret_field not in serialized


def test_plans_are_read_only_code_seeded_authority(client_db: TestClient) -> None:
    _, admin_headers = _platform_admin(client_db)
    plans = client_db.get("/api/v1/platform/plans", headers=admin_headers)
    assert plans.status_code == 200
    assert plans.json()["data"]["items"][0]["authority"] == "CODE_SEEDED_READ_ONLY"
    assert (
        client_db.post(
            "/api/v1/platform/plans", headers=admin_headers, json={}
        ).status_code
        == 405
    )


def test_platform_audit_remains_append_only(client_db: TestClient) -> None:
    target, _ = _register(client_db, "audit-target@example.com")
    _, admin_headers = _platform_admin(client_db)
    client_db.post(
        f"/api/v1/platform/users/{target['id']}/suspend",
        headers=admin_headers,
        json=_confirmed(),
    )

    async def inspect() -> None:
        async with TestSessionLocal() as session:
            event = await session.scalar(
                select(WorkspaceAuditEvent).where(
                    WorkspaceAuditEvent.action == "PLATFORM_USER_SUSPENDED"
                )
            )
            assert event is not None
            event.action = "TAMPERED"
            try:
                await session.commit()
            except RuntimeError as exc:
                assert "append-only" in str(exc)
                await session.rollback()
            else:  # pragma: no cover - safety assertion
                raise AssertionError("Audit mutation unexpectedly succeeded")

    asyncio.run(inspect())


def test_non_admin_cannot_suspend_and_revoke_another_account(
    client_db: TestClient,
) -> None:
    target, target_headers = _register(client_db, "victim@example.com")
    _, attacker_headers = _register(client_db, "attacker@example.com")
    response = client_db.post(
        f"/api/v1/platform/users/{target['id']}/suspend",
        headers=attacker_headers,
        json=_confirmed("Not allowed"),
    )
    assert response.status_code == 403
    assert client_db.get("/api/v1/auth/me", headers=target_headers).status_code == 200
