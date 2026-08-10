"""PostgreSQL-backed human handoff and assignment tests."""

from fastapi.testclient import TestClient

from app.models.workspace_member import WorkspaceRole
from tests.conftest import register_verify_and_login
from tests.test_conversation import _create_conversation, _create_customer
from tests.test_webchat_ai import _install_fake_grounded, _send, _session
from tests.test_workspace_management import _add_member


def _setup(client: TestClient, email: str):
    data, token = register_verify_and_login(client, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    customer = _create_customer(client, token)
    conversation = _create_conversation(client, token, customer, channel="web").json()[
        "data"
    ]
    return data, headers, conversation


def test_manual_handoff_self_assign_reassign_and_return_to_ai(client_db: TestClient):
    owner, headers, conversation = _setup(client_db, "handoff-owner@example.com")
    handed = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/handoff",
        headers=headers,
        json={"reason": "MANUAL_ADMIN"},
    )
    assert handed.status_code == 200
    assert handed.json()["data"]["ai_mode"] == "HUMAN"
    assert handed.json()["data"]["needs_attention"] is True

    self_assigned = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/assign",
        headers=headers,
        json={},
    )
    assert self_assigned.json()["data"]["assigned_user_id"] == owner["user"]["id"]

    member, _ = register_verify_and_login(client_db, email="handoff-member@example.com")
    _add_member(owner["workspace"]["id"], member["user"]["id"], WorkspaceRole.MEMBER)
    reassigned = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/assign",
        headers=headers,
        json={"assigned_user_id": member["user"]["id"]},
    )
    assert reassigned.json()["data"]["assigned_user_id"] == member["user"]["id"]

    unassigned = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/unassign", headers=headers
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["data"]["assigned_user_id"] is None

    returned = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/return-to-ai", headers=headers
    )
    assert returned.status_code == 200
    result = returned.json()["data"]
    assert result["ai_mode"] == "AUTO"
    assert result["handoff_reason"] is None
    assert result["needs_attention"] is False


def test_foreign_assignment_and_cross_workspace_handoff_are_rejected(
    client_db: TestClient,
):
    _, headers, conversation = _setup(client_db, "handoff-a@example.com")
    foreign, foreign_token = register_verify_and_login(
        client_db, email="handoff-b@example.com"
    )
    rejected = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/assign",
        headers=headers,
        json={"assigned_user_id": foreign["user"]["id"]},
    )
    assert rejected.status_code == 422
    assert (
        client_db.patch(
            f"/api/v1/conversations/{conversation['id']}",
            headers=headers,
            json={"assigned_user_id": foreign["user"]["id"]},
        ).status_code
        == 422
    )
    isolated = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/handoff",
        headers={"Authorization": f"Bearer {foreign_token}"},
        json={"reason": "MANUAL_ADMIN"},
    )
    assert isolated.status_code == 404
    assert (
        client_db.post(
            f"/api/v1/conversations/{conversation['id']}/handoff",
            json={"reason": "MANUAL_ADMIN"},
        ).status_code
        == 401
    )


def test_webchat_explicit_handoff_is_idempotent_and_stops_ai(
    client_db: TestClient, monkeypatch
):
    grounded = _install_fake_grounded(monkeypatch)
    owner, token = register_verify_and_login(client_db, email="handoff-web@example.com")
    webchat = _session(client_db, owner["workspace"]["slug"])

    first = _send(client_db, webchat, "handoff-1", "ขอคุยกับเจ้าหน้าที่")
    retry = _send(client_db, webchat, "handoff-1", "ขอคุยกับเจ้าหน้าที่")
    assert first.status_code == retry.status_code == 201
    assert first.json()["data"] == retry.json()["data"]
    assert first.json()["data"]["assistant"]["type"] == "HUMAN_HANDOFF"
    assert grounded.calls == 0

    later = _send(client_db, webchat, "handoff-2", "normal question")
    assert later.json()["data"]["assistant"]["type"] == "HUMAN_MODE"
    assert grounded.calls == 0
    notifications = client_db.get(
        "/api/v1/notifications", headers={"Authorization": f"Bearer {token}"}
    ).json()["data"]["items"]
    handoffs = [
        item for item in notifications if item["type"] == "CONVERSATION_HANDOFF"
    ]
    assert len(handoffs) == 1
    assert all("ขอคุย" not in item["body"] for item in notifications)
