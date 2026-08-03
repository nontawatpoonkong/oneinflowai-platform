"""Create Workspace API test."""

from fastapi.testclient import TestClient

from tests.conftest import register_verify_and_login


def _register_and_token(client: TestClient) -> str:
    _, token = register_verify_and_login(
        client,
        email="bob@example.com",
        full_name="Bob Example",
    )
    return token


def test_create_workspace_requires_auth(client_db: TestClient) -> None:
    response = client_db.post("/api/v1/workspaces", json={"name": "My Team"})
    assert response.status_code == 401


def test_create_workspace_succeeds(client_db: TestClient) -> None:
    token = _register_and_token(client_db)

    response = client_db.post(
        "/api/v1/workspaces",
        json={"name": "My Team"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "My Team"
    assert data["slug"].startswith("my-team")


def test_registration_uses_company_oriented_name(client_db: TestClient) -> None:
    response = client_db.post(
        "/api/v1/auth/register",
        json={
            "email": "founder@acme.com",
            "password": "supersecret123",
            "full_name": "Founder",
        },
    )
    assert response.status_code == 201
    workspace = response.json()["data"]["workspace"]
    # Display name keeps "Workspace"; slug is the independent canonical id.
    assert workspace["name"] == "Acme Workspace"
    assert workspace["slug"] == "acme"


def test_same_company_domain_gets_unique_slugs(client_db: TestClient) -> None:
    slugs = []
    for email in ("alice@acme.com", "bob@acme.com"):
        response = client_db.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "supersecret123", "full_name": "X"},
        )
        assert response.status_code == 201
        slugs.append(response.json()["data"]["workspace"]["slug"])

    assert slugs[0] == "acme"
    assert slugs[1].startswith("acme-")  # uniqueness suffix applied
    assert slugs[0] != slugs[1]
