"""M4: creating a conversation follows the same rules as changing one.

* An initial assignee must be a member holding conversation.read, like
  POST /conversations/{id}/assign.
* A channel connection must belong to the same Workspace.
* Linking the customer needs guest.read, checked before the id is looked up.
"""

import asyncio
import uuid

from sqlalchemy import func, select

from app.models.conversation import Conversation
from app.models.workspace_member import WorkspaceRole
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_crm import _customer
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

URL = "/api/v1/conversations"


def _world(client, email):
    owner, token = register_verify_and_login(client, email=email)
    return {
        "owner_id": owner["user"]["id"],
        "workspace_id": owner["workspace"]["id"],
        "token": token,
        "headers": _headers(token),
        "customer": _customer(client, token)["id"],
    }


def _member(client, world, email, capabilities):
    user, token = _zero_workspace_account(client, email)
    membership_id = _add_member(world["workspace_id"], user["id"], WorkspaceRole.MEMBER)
    granted = client.put(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}/capabilities",
        headers=_headers(world["token"]),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text
    return user["id"], _headers(token, world["workspace_id"])


def _count(world):
    async def read():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.workspace_id == uuid.UUID(world["workspace_id"]))
            )

    return asyncio.run(read())


def _create(client, headers, customer_id, **fields):
    return client.post(
        URL,
        headers=headers,
        json={"customer_id": customer_id, "channel": "web", **fields},
    )


def test_initial_assignee_follows_assignment_rules(client_db):
    world = _world(client_db, "m4-assign-owner@example.com")
    outsider, _ = register_verify_and_login(client_db, email="m4-outsider@example.com")
    blind_id, _ = _member(client_db, world, "m4-blind@example.com", [])
    reader_id, _ = _member(
        client_db, world, "m4-reader@example.com", ["conversation.read"]
    )
    before = _count(world)
    for assignee in (outsider["user"]["id"], blind_id):
        response = _create(
            client_db, world["headers"], world["customer"], assigned_user_id=assignee
        )
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "INVALID_CONVERSATION_ASSIGNEE"
    assert _count(world) == before
    created = _create(
        client_db, world["headers"], world["customer"], assigned_user_id=reader_id
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["assigned_user_id"] == reader_id


def test_channel_connection_must_belong_to_the_workspace(client_db):
    world = _world(client_db, "m4-channel-owner@example.com")
    other = _world(client_db, "m4-channel-other@example.com")
    connected = client_db.post("/api/v1/channels/webchat", headers=other["headers"])
    assert connected.status_code == 200, connected.text
    foreign_connection = connected.json()["data"]["id"]
    before = _count(world)
    response = _create(
        client_db,
        world["headers"],
        world["customer"],
        channel_connection_id=foreign_connection,
    )
    assert response.status_code == 404, response.text
    assert foreign_connection not in response.text
    assert _count(world) == before


def test_linking_the_customer_needs_guest_read(client_db):
    world = _world(client_db, "m4-guest-owner@example.com")
    _, replier = _member(
        client_db, world, "m4-replier@example.com", ["conversation.reply"]
    )
    before = _count(world)
    bodies = set()
    for customer_id in (world["customer"], str(uuid.uuid4())):
        response = _create(client_db, replier, customer_id)
        assert response.status_code == 403, response.text
        assert "guest.read" in response.json()["message"]
        bodies.add(response.text)
    assert len(bodies) == 1
    assert _count(world) == before
    _, guest_replier = _member(
        client_db,
        world,
        "m4-guest-replier@example.com",
        ["conversation.reply", "guest.read"],
    )
    assert _create(client_db, guest_replier, world["customer"]).status_code == 201
