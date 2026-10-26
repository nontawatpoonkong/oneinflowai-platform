"""Workspace Management API tests (Step 3).

Covers: GET /me, GET by slug, GET list, GET members, PATCH success,
PATCH unauthorized, PATCH forbidden (member), PATCH duplicate slug, and
not-found cases. Runs against a real Postgres via the ``client_db`` fixture.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from tests.conftest import (
    TestSessionLocal,
    provision_active_test_subscription,
    register_verify_and_login,
)


def _register(client: TestClient, email: str, full_name: str = "User") -> dict:
    data, token = register_verify_and_login(
        client,
        email=email,
        full_name=full_name,
    )
    data["token"] = {"access_token": token}
    return data


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _add_member(workspace_id: str, user_id: str, role: WorkspaceRole) -> None:
    async def _insert() -> None:
        async with TestSessionLocal() as session:
            session.add(
                WorkspaceMember(
                    workspace_id=uuid.UUID(workspace_id),
                    user_id=uuid.UUID(user_id),
                    role=role,
                )
            )
            await session.commit()

    asyncio.run(_insert())


# --------------------------------------------------------------- GET /me
def test_get_my_primary_workspace(client_db: TestClient) -> None:
    data = _register(client_db, "founder@acme.com")
    token = data["token"]["access_token"]
    expected_slug = data["workspace"]["slug"]

    response = client_db.get("/api/v1/workspaces/me", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["slug"] == expected_slug


def test_get_my_workspace_requires_auth(client_db: TestClient) -> None:
    assert client_db.get("/api/v1/workspaces/me").status_code == 401


# ---------------------------------------------------------- GET by slug
def test_get_workspace_by_slug_public(client_db: TestClient) -> None:
    _register(client_db, "founder@acme.com")
    # No auth header -> public lookup.
    response = client_db.get("/api/v1/workspaces/acme")
    assert response.status_code == 200
    assert response.json()["data"]["slug"] == "acme"


def test_get_workspace_by_slug_not_found(client_db: TestClient) -> None:
    response = client_db.get("/api/v1/workspaces/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


# --------------------------------------------------------------- GET list
def test_list_user_workspaces(client_db: TestClient) -> None:
    data = _register(client_db, "founder@acme.com")
    token = data["token"]["access_token"]
    # One from registration + one explicitly created = 2.
    subscription_id = provision_active_test_subscription(data["user"]["id"])
    client_db.post(
        "/api/v1/workspaces",
        json={"name": "Side Project", "subscription_id": subscription_id},
        headers=_auth(token),
    )

    response = client_db.get("/api/v1/workspaces", headers=_auth(token))
    assert response.status_code == 200
    slugs = {ws["slug"] for ws in response.json()["data"]}
    assert "acme" in slugs
    assert len(response.json()["data"]) == 2


# ------------------------------------------------------------ GET members
def test_list_members_includes_owner(client_db: TestClient) -> None:
    data = _register(client_db, "founder@acme.com")
    token = data["token"]["access_token"]
    workspace_id = data["workspace"]["id"]

    response = client_db.get(
        f"/api/v1/workspaces/{workspace_id}/members", headers=_auth(token)
    )
    assert response.status_code == 200
    members = response.json()["data"]
    assert len(members) == 1
    assert members[0]["role"] == "owner"
    assert members[0]["email"] == "founder@acme.com"


def test_list_members_forbidden_for_non_member(client_db: TestClient) -> None:
    owner = _register(client_db, "founder@acme.com")
    outsider = _register(client_db, "outsider@globex.com")
    workspace_id = owner["workspace"]["id"]

    response = client_db.get(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers=_auth(outsider["token"]["access_token"]),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_list_members_workspace_not_found(client_db: TestClient) -> None:
    token = _register(client_db, "founder@acme.com")["token"]["access_token"]
    response = client_db.get(
        f"/api/v1/workspaces/{uuid.uuid4()}/members", headers=_auth(token)
    )
    assert response.status_code == 404


# ----------------------------------------------------------------- PATCH
def test_patch_updates_name_and_regenerates_slug(client_db: TestClient) -> None:
    data = _register(client_db, "founder@acme.com")
    token = data["token"]["access_token"]
    workspace_id = data["workspace"]["id"]

    response = client_db.patch(
        f"/api/v1/workspaces/{workspace_id}",
        json={"name": "  Rocket Labs  "},  # whitespace trimmed
        headers=_auth(token),
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["name"] == "Rocket Labs"
    assert updated["slug"] == "rocket-labs"


def test_patch_unauthorized_without_token(client_db: TestClient) -> None:
    data = _register(client_db, "founder@acme.com")
    workspace_id = data["workspace"]["id"]
    response = client_db.patch(
        f"/api/v1/workspaces/{workspace_id}", json={"name": "New Name"}
    )
    assert response.status_code == 401


def test_patch_forbidden_for_member(client_db: TestClient) -> None:
    owner = _register(client_db, "founder@acme.com")
    member = _register(client_db, "member@globex.com")
    workspace_id = owner["workspace"]["id"]
    # Make the second user a (non-owner) member of the owner's workspace.
    _add_member(workspace_id, member["user"]["id"], WorkspaceRole.MEMBER)

    response = client_db.patch(
        f"/api/v1/workspaces/{workspace_id}",
        json={"name": "Hijacked"},
        headers=_auth(member["token"]["access_token"]),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_patch_duplicate_slug_conflict(client_db: TestClient) -> None:
    _register(client_db, "alice@acme.com")  # owns slug "acme"
    globex = _register(client_db, "bob@globex.com")  # owns slug "globex"
    globex_id = globex["workspace"]["id"]

    # Rename globex -> "Acme" whose slug collides with the existing "acme".
    response = client_db.patch(
        f"/api/v1/workspaces/{globex_id}",
        json={"name": "Acme"},
        headers=_auth(globex["token"]["access_token"]),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SLUG_ALREADY_EXISTS"


def test_patch_workspace_not_found(client_db: TestClient) -> None:
    token = _register(client_db, "founder@acme.com")["token"]["access_token"]
    response = client_db.patch(
        f"/api/v1/workspaces/{uuid.uuid4()}",
        json={"name": "Whatever"},
        headers=_auth(token),
    )
    assert response.status_code == 404


def test_patch_rejects_empty_name(client_db: TestClient) -> None:
    data = _register(client_db, "founder@acme.com")
    token = data["token"]["access_token"]
    workspace_id = data["workspace"]["id"]
    response = client_db.patch(
        f"/api/v1/workspaces/{workspace_id}",
        json={"name": "   "},
        headers=_auth(token),
    )
    assert response.status_code == 422
