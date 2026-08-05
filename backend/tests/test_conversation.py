"""Conversation & message API tests (Sprint 3)."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import register_verify_and_login

CONV_URL = "/api/v1/conversations"


def _token(client: TestClient, email: str) -> str:
    _, token = register_verify_and_login(client, email=email)
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_customer(client: TestClient, token: str, name: str = "Alice") -> str:
    response = client.post(
        "/api/v1/customers", json={"display_name": name}, headers=_auth(token)
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _create_conversation(
    client: TestClient, token: str, customer_id: str, **fields
) -> "object":
    payload = {"customer_id": customer_id, "channel": "line"}
    payload.update(fields)
    return client.post(CONV_URL, json=payload, headers=_auth(token))


# ----------------------------------------------------------- Conversations
def test_create_conversation(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    customer_id = _create_customer(client_db, token)

    response = _create_conversation(
        client_db, token, customer_id, subject="Order issue", channel="web"
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["customer_id"] == customer_id
    assert data["status"] == "open"
    assert data["channel"] == "web"
    assert data["last_message_at"] is None


def test_create_conversation_requires_valid_customer(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    response = _create_conversation(client_db, token, str(uuid.uuid4()))
    assert response.status_code == 404


def test_create_conversation_rejects_invalid_channel(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    customer_id = _create_customer(client_db, token)
    response = _create_conversation(client_db, token, customer_id, channel="sms")
    assert response.status_code == 422


def test_get_conversation(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    customer_id = _create_customer(client_db, token)
    conv_id = _create_conversation(client_db, token, customer_id).json()["data"]["id"]

    got = client_db.get(f"{CONV_URL}/{conv_id}", headers=_auth(token))
    assert got.status_code == 200
    assert got.json()["data"]["id"] == conv_id


def test_get_missing_conversation_returns_404(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    response = client_db.get(f"{CONV_URL}/{uuid.uuid4()}", headers=_auth(token))
    assert response.status_code == 404


def test_update_conversation_status(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    customer_id = _create_customer(client_db, token)
    conv_id = _create_conversation(client_db, token, customer_id).json()["data"]["id"]

    response = client_db.patch(
        f"{CONV_URL}/{conv_id}",
        json={"status": "resolved"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "resolved"


def test_list_conversations_pagination(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    customer_id = _create_customer(client_db, token)
    for i in range(5):
        _create_conversation(client_db, token, customer_id, subject=f"Topic {i}")

    page1 = client_db.get(
        CONV_URL, params={"page": 1, "page_size": 2}, headers=_auth(token)
    ).json()["data"]
    assert page1["total"] == 5
    assert page1["total_pages"] == 3
    assert len(page1["items"]) == 2


def test_list_conversations_search_and_filter(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    customer_id = _create_customer(client_db, token)
    _create_conversation(
        client_db, token, customer_id, subject="Refund request", channel="line"
    )
    _create_conversation(
        client_db, token, customer_id, subject="General question", channel="email"
    )

    search = client_db.get(
        CONV_URL, params={"q": "Refund"}, headers=_auth(token)
    ).json()["data"]
    assert search["total"] == 1
    assert search["items"][0]["subject"] == "Refund request"

    by_channel = client_db.get(
        CONV_URL, params={"channel": "email"}, headers=_auth(token)
    ).json()["data"]
    assert by_channel["total"] == 1
    assert by_channel["items"][0]["channel"] == "email"


def test_search_by_customer_name_via_join(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    # Customer with a distinctive display_name/full_name.
    cust = client_db.post(
        "/api/v1/customers",
        json={"display_name": "Zorro", "full_name": "Diego Vega"},
        headers=_auth(token),
    ).json()["data"]["id"]
    _create_conversation(client_db, token, cust, subject="Generic subject")

    # Match on customer.display_name.
    by_display = client_db.get(
        CONV_URL, params={"q": "Zorro"}, headers=_auth(token)
    ).json()["data"]
    assert by_display["total"] == 1

    # Match on customer.full_name.
    by_full = client_db.get(
        CONV_URL, params={"q": "Diego"}, headers=_auth(token)
    ).json()["data"]
    assert by_full["total"] == 1

    # Match on conversation.subject still works.
    by_subject = client_db.get(
        CONV_URL, params={"q": "Generic"}, headers=_auth(token)
    ).json()["data"]
    assert by_subject["total"] == 1


def test_conversation_workspace_isolation(client_db: TestClient) -> None:
    token_a = _token(client_db, "a@acme.com")
    token_b = _token(client_db, "b@globex.com")
    customer_id = _create_customer(client_db, token_a)
    conv_id = _create_conversation(client_db, token_a, customer_id).json()["data"]["id"]

    assert client_db.get(CONV_URL, headers=_auth(token_b)).json()["data"]["total"] == 0
    assert (
        client_db.get(f"{CONV_URL}/{conv_id}", headers=_auth(token_b)).status_code
        == 404
    )
    assert (
        client_db.patch(
            f"{CONV_URL}/{conv_id}",
            json={"status": "closed"},
            headers=_auth(token_b),
        ).status_code
        == 404
    )


def test_conversation_requires_auth(client_db: TestClient) -> None:
    assert client_db.get(CONV_URL).status_code == 401
    assert (
        client_db.post(
            CONV_URL, json={"customer_id": str(uuid.uuid4()), "channel": "web"}
        ).status_code
        == 401
    )


# ---------------------------------------------------------------- Messages
def _setup_conversation(client: TestClient, token: str) -> str:
    customer_id = _create_customer(client, token)
    return _create_conversation(client, token, customer_id).json()["data"]["id"]


def test_create_message_updates_last_message_at(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    conv_id = _setup_conversation(client_db, token)

    response = client_db.post(
        f"{CONV_URL}/{conv_id}/messages",
        json={"sender_type": "customer", "content": "Hello there"},
        headers=_auth(token),
    )
    assert response.status_code == 201
    assert response.json()["data"]["content"] == "Hello there"
    assert response.json()["data"]["message_type"] == "text"

    conv = client_db.get(f"{CONV_URL}/{conv_id}", headers=_auth(token)).json()["data"]
    assert conv["last_message_at"] is not None


def test_create_message_requires_conversation(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    response = client_db.post(
        f"{CONV_URL}/{uuid.uuid4()}/messages",
        json={"sender_type": "agent", "content": "Hi"},
        headers=_auth(token),
    )
    assert response.status_code == 404


def test_create_message_rejects_empty_content(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    conv_id = _setup_conversation(client_db, token)
    response = client_db.post(
        f"{CONV_URL}/{conv_id}/messages",
        json={"sender_type": "agent", "content": "   "},
        headers=_auth(token),
    )
    assert response.status_code == 422


def test_list_messages_ordered_asc(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    conv_id = _setup_conversation(client_db, token)
    for content in ("first", "second", "third"):
        client_db.post(
            f"{CONV_URL}/{conv_id}/messages",
            json={"sender_type": "customer", "content": content},
            headers=_auth(token),
        )

    listing = client_db.get(
        f"{CONV_URL}/{conv_id}/messages", headers=_auth(token)
    ).json()["data"]
    assert listing["total"] == 3
    assert [m["content"] for m in listing["items"]] == ["first", "second", "third"]


def test_list_messages_pagination(client_db: TestClient) -> None:
    token = _token(client_db, "owner@acme.com")
    conv_id = _setup_conversation(client_db, token)
    for i in range(4):
        client_db.post(
            f"{CONV_URL}/{conv_id}/messages",
            json={"sender_type": "customer", "content": f"msg {i}"},
            headers=_auth(token),
        )

    page = client_db.get(
        f"{CONV_URL}/{conv_id}/messages",
        params={"page": 1, "page_size": 2},
        headers=_auth(token),
    ).json()["data"]
    assert page["total"] == 4
    assert page["total_pages"] == 2
    assert len(page["items"]) == 2


def test_messages_require_auth(client_db: TestClient) -> None:
    conv_id = uuid.uuid4()
    assert client_db.get(f"{CONV_URL}/{conv_id}/messages").status_code == 401
    assert (
        client_db.post(
            f"{CONV_URL}/{conv_id}/messages",
            json={"sender_type": "agent", "content": "x"},
        ).status_code
        == 401
    )


def test_messages_workspace_isolation(client_db: TestClient) -> None:
    token_a = _token(client_db, "a@acme.com")
    token_b = _token(client_db, "b@globex.com")
    conv_id = _setup_conversation(client_db, token_a)

    # B cannot post to or read A's conversation messages.
    assert (
        client_db.post(
            f"{CONV_URL}/{conv_id}/messages",
            json={"sender_type": "agent", "content": "intrude"},
            headers=_auth(token_b),
        ).status_code
        == 404
    )
    assert (
        client_db.get(
            f"{CONV_URL}/{conv_id}/messages", headers=_auth(token_b)
        ).status_code
        == 404
    )
