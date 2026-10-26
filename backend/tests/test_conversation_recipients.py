"""H3: conversation notices only reach people who may read the conversation.

A conversation can be assigned only to a member holding conversation.read.
Handoff and new-customer-message notices go to the assignee while they are
still a member holding conversation.read; otherwise owners and admins get
them. Refused assignments write nothing and notify no one.
"""

import asyncio
import uuid

from sqlalchemy import select

from app.models.conversation import Conversation
from app.models.notification import Notification, NotificationType
from app.models.workspace_member import WorkspaceRole
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_crm import _conversation, _customer
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)


def _world(client, email):
    owner, token = register_verify_and_login(client, email=email)
    customer = _customer(client, token)
    return {
        "owner_id": owner["user"]["id"],
        "workspace_id": owner["workspace"]["id"],
        "token": token,
        "headers": _headers(token),
        "conversation": _conversation(client, token, customer["id"]),
    }


def _member(client, world, email, capabilities):
    user, _ = _zero_workspace_account(client, email)
    membership_id = _add_member(world["workspace_id"], user["id"], WorkspaceRole.MEMBER)
    _grant(client, world, membership_id, capabilities)
    return user["id"], membership_id


def _grant(client, world, membership_id, capabilities):
    granted = client.put(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}/capabilities",
        headers=_headers(world["token"]),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text


def _assign(client, world, user_id):
    return client.post(
        f"/api/v1/conversations/{world['conversation']}/assign",
        headers=world["headers"],
        json={"assigned_user_id": user_id},
    )


def _notices(world, kind):
    async def read():
        async with TestSessionLocal() as session:
            rows = await session.scalars(
                select(Notification.recipient_user_id).where(
                    Notification.workspace_id == uuid.UUID(world["workspace_id"]),
                    Notification.type == kind,
                )
            )
            return sorted(str(row) for row in rows)

    return asyncio.run(read())


def _conversation_row(world):
    async def read():
        async with TestSessionLocal() as session:
            row = await session.get(Conversation, uuid.UUID(world["conversation"]))
            return row.assigned_user_id, row.assigned_at, row.updated_at

    return asyncio.run(read())


def _customer_message(client, world, text):
    response = client.post(
        f"/api/v1/conversations/{world['conversation']}/messages",
        headers=world["headers"],
        json={"sender_type": "customer", "content": text},
    )
    assert response.status_code == 201, response.text


def test_assignee_needs_conversation_read(client_db):
    world = _world(client_db, "h3-assign-owner@example.com")
    blind_id, _ = _member(client_db, world, "h3-blind@example.com", ["action.read"])
    before = _conversation_row(world)
    notices_before = _notices(world, NotificationType.CONVERSATION_ASSIGNED)
    refused = _assign(client_db, world, blind_id)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "INVALID_CONVERSATION_ASSIGNEE"
    assert "Need a quiet room" not in refused.text
    assert _conversation_row(world) == before
    assert _notices(world, NotificationType.CONVERSATION_ASSIGNED) == notices_before

    reader_id, _ = _member(
        client_db, world, "h3-reader@example.com", ["conversation.read"]
    )
    assigned = _assign(client_db, world, reader_id)
    assert assigned.status_code == 200, assigned.text
    assert _notices(world, NotificationType.CONVERSATION_ASSIGNED) == [reader_id]


def test_new_message_notice_follows_the_assignees_current_access(client_db):
    world = _world(client_db, "h3-message-owner@example.com")
    reader_id, membership_id = _member(
        client_db, world, "h3-message-reader@example.com", ["conversation.read"]
    )
    assert _assign(client_db, world, reader_id).status_code == 200
    before = _notices(world, NotificationType.NEW_CUSTOMER_MESSAGE)
    _customer_message(client_db, world, "Is breakfast included?")
    after_first = _notices(world, NotificationType.NEW_CUSTOMER_MESSAGE)
    assert sorted(set(after_first) - set(before)) == [reader_id]

    _grant(client_db, world, membership_id, [])
    _customer_message(client_db, world, "Hello again")
    after_revoke = _notices(world, NotificationType.NEW_CUSTOMER_MESSAGE)
    # The revoked assignee gets nothing new; owners and admins are told.
    assert after_revoke.count(reader_id) == after_first.count(reader_id)
    assert (
        after_revoke.count(world["owner_id"])
        == after_first.count(world["owner_id"]) + 1
    )


def test_handoff_notice_skips_a_removed_assignee(client_db):
    world = _world(client_db, "h3-handoff-owner@example.com")
    reader_id, membership_id = _member(
        client_db, world, "h3-handoff-reader@example.com", ["conversation.read"]
    )
    assert _assign(client_db, world, reader_id).status_code == 200
    removed = client_db.delete(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}",
        headers=_headers(world["token"]),
    )
    assert removed.status_code in {200, 204}, removed.text
    handed = client_db.post(
        f"/api/v1/conversations/{world['conversation']}/handoff",
        headers=world["headers"],
        json={"reason": "MANUAL_ADMIN"},
    )
    assert handed.status_code == 200, handed.text
    assert _notices(world, NotificationType.CONVERSATION_HANDOFF) == [world["owner_id"]]
