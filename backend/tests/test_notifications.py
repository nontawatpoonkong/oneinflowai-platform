"""Notification isolation, deduplication, and read-state tests."""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_conversation import _create_conversation, _create_customer
from tests.test_workspace_management import _add_member


def _setup(client: TestClient):
    owner, owner_token = register_verify_and_login(
        client, email="notify-owner@example.com"
    )
    member, member_token = register_verify_and_login(
        client, email="notify-member@example.com"
    )
    _add_member(owner["workspace"]["id"], member["user"]["id"], WorkspaceRole.MEMBER)

    async def select_joined_workspace():
        async with TestSessionLocal() as session:
            await session.execute(
                delete(WorkspaceMember).where(
                    WorkspaceMember.user_id == uuid.UUID(member["user"]["id"]),
                    WorkspaceMember.workspace_id
                    != uuid.UUID(owner["workspace"]["id"]),
                )
            )
            await session.commit()

    asyncio.run(select_joined_workspace())
    customer = _create_customer(client, owner_token)
    conversation = _create_conversation(client, owner_token, customer).json()["data"]
    return owner, owner_token, member, member_token, conversation


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_customer_unread_is_per_member_and_mark_read_isolated(client_db: TestClient):
    _, owner_token, _, member_token, conversation = _setup(client_db)
    created = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=_headers(owner_token),
        json={"sender_type": "customer", "content": "Need assistance"},
    )
    assert created.status_code == 201
    owner_view = client_db.get(
        f"/api/v1/conversations/{conversation['id']}", headers=_headers(owner_token)
    ).json()["data"]
    member_view = client_db.get(
        f"/api/v1/conversations/{conversation['id']}", headers=_headers(member_token)
    ).json()["data"]
    assert owner_view["unread_count"] == member_view["unread_count"] == 1

    marked = client_db.post(
        f"/api/v1/conversations/{conversation['id']}/read",
        headers=_headers(owner_token),
    )
    assert marked.json()["data"]["unread_count"] == 0
    assert (
        client_db.get(
            f"/api/v1/conversations/{conversation['id']}",
            headers=_headers(member_token),
        ).json()["data"]["unread_count"]
        == 1
    )

    client_db.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=_headers(owner_token),
        json={"sender_type": "ai", "content": "AI response"},
    )
    assert (
        client_db.get(
            f"/api/v1/conversations/{conversation['id']}", headers=_headers(owner_token)
        ).json()["data"]["unread_count"]
        == 0
    )


def test_notification_recipient_isolation_read_all_and_assignment_dedup(
    client_db: TestClient,
):
    owner, owner_token, member, member_token, conversation = _setup(client_db)
    url = f"/api/v1/conversations/{conversation['id']}/assign"
    for _ in range(2):
        assert (
            client_db.post(
                url,
                headers=_headers(owner_token),
                json={"assigned_user_id": member["user"]["id"]},
            ).status_code
            == 200
        )
    member_data = client_db.get(
        "/api/v1/notifications", headers=_headers(member_token)
    ).json()["data"]
    assigned = [
        item for item in member_data["items"] if item["type"] == "CONVERSATION_ASSIGNED"
    ]
    assert len(assigned) == 1
    assert member_data["unread_count"] == 1
    assert (
        client_db.post(
            f"/api/v1/notifications/{assigned[0]['id']}/read",
            headers=_headers(owner_token),
        ).status_code
        == 404
    )
    assert (
        client_db.post(
            "/api/v1/notifications/read-all", headers=_headers(member_token)
        ).json()["data"]["marked_read"]
        == 1
    )
    assert (
        client_db.get("/api/v1/notifications", headers=_headers(member_token)).json()[
            "data"
        ]["unread_count"]
        == 0
    )
