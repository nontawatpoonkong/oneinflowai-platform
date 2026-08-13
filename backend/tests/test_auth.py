"""Register / login / current-user API tests (against a real Postgres)."""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.billing import WorkspaceSubscription
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from tests.conftest import TestSessionLocal

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


def _register(client: TestClient, **overrides) -> dict:
    payload = {
        "email": "alice@example.com",
        "password": "supersecret123",
        "full_name": "Alice Example",
    }
    payload.update(overrides)
    return client.post(REGISTER_URL, json=payload)


def test_register_creates_user_only_and_requires_workspace_onboarding(
    client_db: TestClient,
) -> None:
    response = _register(client_db)

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True

    data = body["data"]
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["full_name"] == "Alice Example"
    assert "id" in data["user"]

    assert data["workspace_required"] is True
    assert "workspace" not in data

    assert data["verification_required"] is True
    assert data["verification_type"] == "EMAIL_OTP"
    assert data["verification_expires_in"] == 300
    assert data["resend_after"] == 60
    assert "token" not in data

    async def workspace_counts():
        async with TestSessionLocal() as session:
            return (
                await session.scalar(select(func.count()).select_from(Workspace)),
                await session.scalar(
                    select(func.count()).select_from(WorkspaceMember)
                ),
                await session.scalar(
                    select(func.count()).select_from(WorkspaceSubscription)
                ),
            )

    assert asyncio.run(workspace_counts()) == (0, 0, 0)


def test_register_rejects_duplicate_email(client_db: TestClient) -> None:
    assert _register(client_db).status_code == 201

    duplicate = _register(client_db)
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["success"] is False
    assert body["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_register_validates_password_length(client_db: TestClient) -> None:
    response = _register(client_db, password="short")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_succeeds_with_valid_credentials(
    client_db: TestClient, fake_email_provider
) -> None:
    _register(client_db)
    client_db.post(
        "/api/v1/auth/verify-email",
        json={"email": "alice@example.com", "otp": fake_email_provider.latest_otp},
    )

    response = client_db.post(
        LOGIN_URL,
        json={"email": "alice@example.com", "password": "supersecret123"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert data["expires_in"] == 1800

    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert client_db.get("/api/v1/workspaces", headers=headers).json()["data"] == []
    required = client_db.get("/api/v1/workspaces/me", headers=headers)
    assert required.status_code == 404
    assert required.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    assert client_db.get("/api/v1/channels", headers=headers).status_code == 404


def test_zero_workspace_user_explicitly_creates_workspace_as_only_owner(
    client_db: TestClient, fake_email_provider
) -> None:
    registered = _register(client_db).json()["data"]
    client_db.post(
        "/api/v1/auth/verify-email",
        json={"email": "alice@example.com", "otp": fake_email_provider.latest_otp},
    )
    token = client_db.post(
        LOGIN_URL,
        json={"email": "alice@example.com", "password": "supersecret123"},
    ).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client_db.post(
        "/api/v1/workspaces", headers=headers, json={"name": "ABC Hotel"}
    )

    assert created.status_code == 201
    workspace = created.json()["data"]
    assert workspace["owner_id"] == registered["user"]["id"]
    members = client_db.get(
        f"/api/v1/workspaces/{workspace['id']}/members", headers=headers
    ).json()["data"]
    assert len(members) == 1
    assert members[0]["role"] == "owner"
    assert client_db.get("/api/v1/channels", headers=headers).json()["data"] == []


def test_login_is_case_insensitive_on_email(
    client_db: TestClient, fake_email_provider
) -> None:
    _register(client_db)
    client_db.post(
        "/api/v1/auth/verify-email",
        json={"email": "alice@example.com", "otp": fake_email_provider.latest_otp},
    )
    response = client_db.post(
        LOGIN_URL,
        json={"email": "ALICE@example.com", "password": "supersecret123"},
    )
    assert response.status_code == 200


def test_login_fails_with_wrong_password(client_db: TestClient) -> None:
    _register(client_db)
    response = client_db.post(
        LOGIN_URL,
        json={"email": "alice@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_returns_current_user_with_token(client_db: TestClient) -> None:
    _register(client_db)
    provider = client_db.app.state.fake_email_provider
    client_db.post(
        "/api/v1/auth/verify-email",
        json={"email": "alice@example.com", "otp": provider.latest_otp},
    )
    token = client_db.post(
        LOGIN_URL,
        json={"email": "alice@example.com", "password": "supersecret123"},
    ).json()["data"]["access_token"]

    response = client_db.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "alice@example.com"


def test_me_requires_authentication(client_db: TestClient) -> None:
    response = client_db.get(ME_URL)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
