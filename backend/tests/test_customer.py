"""Customer API tests (Sprint 2).

Covers CRUD, pagination, search, sorting, filtering, soft delete, workspace
isolation, authorization, and validation. Runs against a real Postgres.
"""

import uuid

from fastapi.testclient import TestClient

CUSTOMERS_URL = "/api/v1/customers"


def _token(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret123", "full_name": "Owner"},
    )
    assert response.status_code == 201
    return response.json()["data"]["token"]["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create(client: TestClient, token: str, **fields) -> dict:
    payload = {"display_name": "Alice"}
    payload.update(fields)
    response = client.post(CUSTOMERS_URL, json=payload, headers=_auth(token))
    return response


# ------------------------------------------------------------------ CRUD
def test_create_get_update_delete_flow(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")

    created = _create(
        client_db, token, display_name="  Alice  ", email="alice@corp.com"
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["display_name"] == "Alice"  # trimmed
    assert data["status"] == "active"
    customer_id = data["id"]

    got = client_db.get(f"{CUSTOMERS_URL}/{customer_id}", headers=_auth(token))
    assert got.status_code == 200
    assert got.json()["data"]["id"] == customer_id

    patched = client_db.patch(
        f"{CUSTOMERS_URL}/{customer_id}",
        json={"full_name": "Alice Wonderland", "status": "inactive"},
        headers=_auth(token),
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["full_name"] == "Alice Wonderland"
    assert patched.json()["data"]["status"] == "inactive"

    deleted = client_db.delete(f"{CUSTOMERS_URL}/{customer_id}", headers=_auth(token))
    assert deleted.status_code == 200


# ------------------------------------------------------------ Soft delete
def test_soft_delete_hides_customer(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    customer_id = _create(client_db, token).json()["data"]["id"]

    client_db.delete(f"{CUSTOMERS_URL}/{customer_id}", headers=_auth(token))

    # Hidden from get and list after soft delete.
    got = client_db.get(f"{CUSTOMERS_URL}/{customer_id}", headers=_auth(token))
    assert got.status_code == 404
    listing = client_db.get(CUSTOMERS_URL, headers=_auth(token)).json()["data"]
    assert listing["total"] == 0


# ------------------------------------------------------------- Validation
def test_create_rejects_invalid_email(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    response = _create(client_db, token, email="not-an-email")
    assert response.status_code == 422


def test_create_rejects_invalid_phone(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    response = _create(client_db, token, phone="abc123")
    assert response.status_code == 422


def test_create_rejects_empty_display_name(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    response = _create(client_db, token, display_name="   ")
    assert response.status_code == 422


# ------------------------------------------------------------ Pagination
def test_pagination(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    for i in range(5):
        _create(client_db, token, display_name=f"Customer {i}")

    page1 = client_db.get(
        CUSTOMERS_URL, params={"page": 1, "page_size": 2}, headers=_auth(token)
    ).json()["data"]
    assert page1["total"] == 5
    assert page1["page_size"] == 2
    assert page1["total_pages"] == 3
    assert len(page1["items"]) == 2


# ---------------------------------------------------------------- Search
def test_search_matches_multiple_fields(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    _create(client_db, token, display_name="Bob", email="bob@x.com")
    _create(client_db, token, display_name="Carol", phone="+66812345678")
    _create(client_db, token, display_name="Dave", full_name="David Jones")

    by_email = client_db.get(
        CUSTOMERS_URL, params={"q": "bob@x"}, headers=_auth(token)
    ).json()["data"]
    assert by_email["total"] == 1
    assert by_email["items"][0]["display_name"] == "Bob"

    by_fullname = client_db.get(
        CUSTOMERS_URL, params={"q": "David"}, headers=_auth(token)
    ).json()["data"]
    assert by_fullname["total"] == 1
    assert by_fullname["items"][0]["display_name"] == "Dave"


# --------------------------------------------------------------- Sorting
def test_sorting_by_display_name(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    for name in ("Charlie", "Alice", "Bob"):
        _create(client_db, token, display_name=name)

    result = client_db.get(
        CUSTOMERS_URL,
        params={"sort_by": "display_name", "order": "asc"},
        headers=_auth(token),
    ).json()["data"]
    names = [c["display_name"] for c in result["items"]]
    assert names == ["Alice", "Bob", "Charlie"]


# -------------------------------------------------------------- Filtering
def test_filter_by_status(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    _create(client_db, token, display_name="Active One")
    _create(client_db, token, display_name="Inactive One", status="inactive")

    inactive = client_db.get(
        CUSTOMERS_URL, params={"status": "inactive"}, headers=_auth(token)
    ).json()["data"]
    assert inactive["total"] == 1
    assert inactive["items"][0]["display_name"] == "Inactive One"


# ------------------------------------------------------ Workspace isolation
def test_workspace_isolation(client_db: TestClient) -> None:
    token_a = _token(client_db, "a@acme.com")
    token_b = _token(client_db, "b@globex.com")

    customer_id = _create(client_db, token_a, display_name="A-Only").json()["data"][
        "id"
    ]

    # B cannot see A's customer in listing or by id.
    b_list = client_db.get(CUSTOMERS_URL, headers=_auth(token_b)).json()["data"]
    assert b_list["total"] == 0

    assert (
        client_db.get(
            f"{CUSTOMERS_URL}/{customer_id}", headers=_auth(token_b)
        ).status_code
        == 404
    )
    assert (
        client_db.patch(
            f"{CUSTOMERS_URL}/{customer_id}",
            json={"display_name": "Hacked"},
            headers=_auth(token_b),
        ).status_code
        == 404
    )
    assert (
        client_db.delete(
            f"{CUSTOMERS_URL}/{customer_id}", headers=_auth(token_b)
        ).status_code
        == 404
    )


# ---------------------------------------------------------- Authorization
def test_requires_authentication(client_db: TestClient) -> None:
    assert client_db.get(CUSTOMERS_URL).status_code == 401
    assert client_db.post(CUSTOMERS_URL, json={"display_name": "X"}).status_code == 401
    assert client_db.get(f"{CUSTOMERS_URL}/{uuid.uuid4()}").status_code == 401


def test_get_missing_customer_returns_404(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    response = client_db.get(f"{CUSTOMERS_URL}/{uuid.uuid4()}", headers=_auth(token))
    assert response.status_code == 404
