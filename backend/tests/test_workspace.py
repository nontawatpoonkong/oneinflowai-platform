"""Create Workspace API test."""

from fastapi.testclient import TestClient

from tests.conftest import (
    provision_active_test_subscription,
    register_verify_and_login,
)


def _register_and_token(client: TestClient) -> tuple[dict, str]:
    data, token = register_verify_and_login(
        client,
        email="bob@example.com",
        full_name="Bob Example",
    )
    return data, token


def test_create_workspace_requires_auth(client_db: TestClient) -> None:
    response = client_db.post("/api/v1/workspaces", json={"name": "My Team"})
    assert response.status_code == 401


def test_create_workspace_succeeds(client_db: TestClient) -> None:
    data, token = _register_and_token(client_db)
    subscription_id = provision_active_test_subscription(data["user"]["id"])

    response = client_db.post(
        "/api/v1/workspaces",
        json={"name": "My Team", "subscription_id": subscription_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "My Team"
    assert data["slug"].startswith("my-team")


def test_explicit_workspace_creation_gets_unique_slugs(client_db: TestClient) -> None:
    data, token = _register_and_token(client_db)
    headers = {"Authorization": f"Bearer {token}"}
    first_subscription = provision_active_test_subscription(data["user"]["id"])
    second_subscription = provision_active_test_subscription(data["user"]["id"])
    first = client_db.post(
        "/api/v1/workspaces",
        json={"name": "Acme", "subscription_id": first_subscription},
        headers=headers,
    )
    second = client_db.post(
        "/api/v1/workspaces",
        json={"name": "Acme", "subscription_id": second_subscription},
        headers=headers,
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["slug"] == "acme"
    assert second.json()["data"]["slug"].startswith("acme-")
