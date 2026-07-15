"""Focused public WebChat API tests."""

from fastapi.testclient import TestClient

WEBCHAT_URL = "/api/v1/webchat/sessions"


def _workspace_key(client: TestClient, email: str = "webchat@acme.com") -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret123", "full_name": "Owner"},
    )
    assert response.status_code == 201
    return response.json()["data"]["workspace"]["slug"]


def _session(client: TestClient, key: str) -> dict[str, str]:
    response = client.post(
        WEBCHAT_URL,
        json={
            "workspace_key": key,
            "name": "Visitor",
            "language": "th-TH",
            "timezone": "Asia/Bangkok",
            "landing_url": "https://example.com/product",
            "referrer": "https://example.com",
        },
        headers={"User-Agent": "WebChat test"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert set(data) == {"conversation_id", "session_token"}
    return data


def _headers(token: str) -> dict[str, str]:
    return {"X-WebChat-Token": token}


def test_session_creation_and_valid_token_send_read(client_db: TestClient) -> None:
    session = _session(client_db, _workspace_key(client_db))
    url = f"{WEBCHAT_URL}/{session['conversation_id']}/messages"

    sent = client_db.post(
        url,
        json={"content": " สวัสดี "},
        headers=_headers(session["session_token"]),
    )
    assert sent.status_code == 201
    assert sent.json()["data"]["sender_type"] == "customer"
    assert sent.json()["data"]["content"] == "สวัสดี"

    read = client_db.get(url, headers=_headers(session["session_token"]))
    assert read.status_code == 200
    assert read.json()["data"]["items"][0]["content"] == "สวัสดี"


def test_invalid_token_is_rejected(client_db: TestClient) -> None:
    session = _session(client_db, _workspace_key(client_db))
    url = f"{WEBCHAT_URL}/{session['conversation_id']}/messages"
    assert client_db.get(url, headers=_headers("invalid-token")).status_code == 401


def test_token_cannot_access_another_conversation(client_db: TestClient) -> None:
    key = _workspace_key(client_db)
    session_a = _session(client_db, key)
    session_b = _session(client_db, key)
    url_b = f"{WEBCHAT_URL}/{session_b['conversation_id']}/messages"
    response = client_db.get(url_b, headers=_headers(session_a["session_token"]))
    assert response.status_code == 401


def test_workspace_key_not_found(client_db: TestClient) -> None:
    response = client_db.post(
        WEBCHAT_URL,
        json={"workspace_key": "missing-workspace", "name": "Visitor"},
    )
    assert response.status_code == 404


def test_empty_message_is_rejected(client_db: TestClient) -> None:
    session = _session(client_db, _workspace_key(client_db))
    url = f"{WEBCHAT_URL}/{session['conversation_id']}/messages"
    response = client_db.post(
        url,
        json={"content": "   "},
        headers=_headers(session["session_token"]),
    )
    assert response.status_code == 422
