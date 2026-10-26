"""Post-F4 hardening for Actions, Action Collections and Action Definitions.

* Assignees must hold action.read and action.operate before an Action is
  assigned to them or they are notified about it.
* Reading an Action Collection never writes; expiry is persisted by the next
  locked change instead.
* Creating or changing an Action Definition is audited with field names only.
* Linking a customer or conversation needs guest.read or conversation.read,
  checked before the id is looked up.
* WebChat visitors can only decide collections of their own conversation.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.action import ActionDefinition, ActionRequest
from app.models.action_collection import ActionCollectionSession
from app.models.audit import WorkspaceAuditEvent
from app.models.notification import Notification
from app.models.workspace_member import WorkspaceRole
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_action_authorization import (
    ACTIONS,
    COLLECTIONS,
    SECRET_PHONE,
    _assert_no_secrets,
    _grant,
    _member,
    _state,
    _world,
)
from tests.test_crm import _customer
from tests.test_hotel import _auth
from tests.test_webchat_ai import (
    _install_fake_grounded,
    _send,
    _session,
    _workspace,
)

DEFINITION_DESCRIPTION = f"Call the guest back on {SECRET_PHONE}"


def _assignment_notifications(workspace_id, recipient_id):
    async def count():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.workspace_id == uuid.UUID(workspace_id),
                    Notification.recipient_user_id == uuid.UUID(recipient_id),
                )
            )

    return asyncio.run(count())


def test_assignment_requires_assignee_action_capabilities(client_db):
    world = _world(client_db, "hard-assign-owner@example.com")
    operator, _, _ = _member(
        client_db,
        world,
        "hard-assign-operator@example.com",
        ["action.read", "action.operate"],
    )
    assignees = {
        name: _member(client_db, world, f"hard-assignee-{name}@example.com", caps)
        for name, caps in (
            ("none", []),
            ("read", ["action.read"]),
            ("operate", ["action.operate"]),
            ("both", ["action.read", "action.operate"]),
        )
    }
    before = _state(world["workspace_id"])
    for name in ("none", "read", "operate"):
        assignee_id = assignees[name][2]
        response = client_db.post(
            f"{ACTIONS}/{world['action']}/assign",
            headers=operator,
            json={"user_id": assignee_id},
        )
        assert response.status_code == 422, (name, response.text)
        assert response.json()["error"]["code"] == "ACTION_ASSIGNMENT_INVALID"
        _assert_no_secrets(response, world)
        assert _assignment_notifications(world["workspace_id"], assignee_id) == 0
    # A refused assignment writes no state, event or notification.
    assert _state(world["workspace_id"]) == before

    assignee_id = assignees["both"][2]
    assigned = client_db.post(
        f"{ACTIONS}/{world['action']}/assign",
        headers=operator,
        json={"user_id": assignee_id},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["data"]["assigned_to_user_id"] == assignee_id
    assert _assignment_notifications(world["workspace_id"], assignee_id) == 1
    # Owners and admins hold both capabilities through the role baseline.
    _, _, admin_id = _member(
        client_db, world, "hard-assign-admin@example.com", [], WorkspaceRole.ADMIN
    )
    second = client_db.post(
        ACTIONS,
        headers=_auth(world["token"]),
        json={
            "action_definition_id": world["definition"],
            "payload": {"guest_phone": SECRET_PHONE},
        },
    ).json()["data"]
    to_admin = client_db.post(
        f"{ACTIONS}/{second['id']}/assign",
        headers=operator,
        json={"user_id": admin_id},
    )
    assert to_admin.status_code == 200, to_admin.text


def test_revoked_assignee_cannot_receive_new_assignments(client_db):
    world = _world(client_db, "hard-revoke-owner@example.com")
    _, membership_id, assignee_id = _member(
        client_db,
        world,
        "hard-revoke-assignee@example.com",
        ["action.read", "action.operate"],
    )
    _grant(client_db, world, membership_id, ["action.read"])
    before = _state(world["workspace_id"])
    response = client_db.post(
        f"{ACTIONS}/{world['action']}/assign",
        headers=_auth(world["token"]),
        json={"user_id": assignee_id},
    )
    assert response.status_code == 422, response.text
    assert _state(world["workspace_id"]) == before


def _collection_row(collection_id):
    async def read():
        async with TestSessionLocal() as session:
            row = await session.get(ActionCollectionSession, uuid.UUID(collection_id))
            return (
                row.status.value,
                row.updated_at,
                row.confirmation_token_hash,
                row.confirmation_expires_at,
            )

    return asyncio.run(read())


def _expire_collection(collection_id):
    async def expire():
        async with TestSessionLocal() as session:
            row = await session.get(ActionCollectionSession, uuid.UUID(collection_id))
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire())


def test_get_collection_is_read_only_and_expiry_persists_on_change(client_db):
    world = _world(client_db, "hard-get-owner@example.com")
    owner = _auth(world["token"])
    path = f"{COLLECTIONS}/{world['collection']}"
    live_before = _collection_row(world["collection"])
    fresh = client_db.get(path, headers=owner)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["data"]["session"]["status"] == "AWAITING_CONFIRMATION"
    assert _collection_row(world["collection"]) == live_before

    _expire_collection(world["collection"])
    before = _collection_row(world["collection"])
    state_before = _state(world["workspace_id"])
    for _ in range(2):
        expired = client_db.get(path, headers=owner)
        assert expired.status_code == 409, expired.text
        assert expired.json()["message"] == "Action collection session has expired"
        _assert_no_secrets(expired, world)
    # GET is read-only: status, token hash and timestamps are untouched.
    assert _collection_row(world["collection"]) == before
    assert before[0] == "AWAITING_CONFIRMATION"
    assert _state(world["workspace_id"]) == state_before

    # The next locked change still persists the expiry and refuses the change.
    cancelled = client_db.post(f"{path}/cancel", headers=owner)
    assert cancelled.status_code == 409, cancelled.text
    status, _, token_hash, confirmation_expires_at = _collection_row(
        world["collection"]
    )
    assert (status, token_hash, confirmation_expires_at) == ("EXPIRED", None, None)
    confirm = client_db.post(
        f"{path}/confirm",
        headers=owner,
        json={"confirmation_token": world["confirmation_token"]},
    )
    assert confirm.status_code == 409, confirm.text


def _definition_audit(workspace_id):
    async def read():
        async with TestSessionLocal() as session:
            rows = await session.scalars(
                select(WorkspaceAuditEvent)
                .where(
                    WorkspaceAuditEvent.workspace_id == uuid.UUID(workspace_id),
                    WorkspaceAuditEvent.resource_type == "ActionDefinition",
                )
                .order_by(WorkspaceAuditEvent.occurred_at, WorkspaceAuditEvent.id)
            )
            return [
                {
                    "action": row.action,
                    "area": row.area,
                    "actor": str(row.actor_user_id),
                    "actor_type": row.actor_type,
                    "resource_id": str(row.resource_id),
                    "metadata": row.safe_metadata,
                }
                for row in rows
            ]

    return asyncio.run(read())


def _definition_row(definition_id):
    async def read():
        async with TestSessionLocal() as session:
            row = await session.get(ActionDefinition, uuid.UUID(definition_id))
            return row.name, row.description, row.is_active, row.updated_at

    return asyncio.run(read())


def test_definition_changes_are_audited_without_guest_data(client_db):
    world = _world(client_db, "hard-audit-owner@example.com")
    owner_id = world["owner"]["user"]["id"]
    owner = _auth(world["token"])
    initial = _definition_audit(world["workspace_id"])
    # _world created one definition before this test looked.
    assert [item["action"] for item in initial] == ["ACTION_DEFINITION_CREATED"]
    created = client_db.post(
        f"{ACTIONS}/definitions",
        headers=owner,
        json={
            "key": "vip_followup",
            "name": "VIP follow-up",
            "description": DEFINITION_DESCRIPTION,
            "required_fields": [
                {
                    "key": "guest_phone",
                    "label": "Guest phone",
                    "type": "string",
                    "required": True,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    definition_id = created.json()["data"]["id"]
    updated = client_db.patch(
        f"{ACTIONS}/definitions/{definition_id}",
        headers=owner,
        json={"name": "VIP follow-up call", "is_active": False},
    )
    assert updated.status_code == 200, updated.text
    unchanged = client_db.patch(
        f"{ACTIONS}/definitions/{definition_id}",
        headers=owner,
        json={"name": "VIP follow-up call"},
    )
    assert unchanged.status_code == 200, unchanged.text

    events = _definition_audit(world["workspace_id"])[1:]
    assert events == [
        {
            "action": "ACTION_DEFINITION_CREATED",
            "area": "SETTINGS",
            "actor": owner_id,
            "actor_type": "USER",
            "resource_id": definition_id,
            "metadata": {
                "definition_key": "vip_followup",
                "fields": ["guest_phone"],
                "is_active": True,
            },
        },
        {
            "action": "ACTION_DEFINITION_UPDATED",
            "area": "SETTINGS",
            "actor": owner_id,
            "actor_type": "USER",
            "resource_id": definition_id,
            "metadata": {"changed_fields": ["is_active", "name"]},
        },
    ]
    # Names, descriptions, labels and anything guest-shaped stay out.
    serialized = str(events)
    for value in (SECRET_PHONE, "VIP follow-up", "Guest phone", "Call the guest"):
        assert value not in serialized

    # Members stay OWNER/ADMIN-gated: no change, no audit row.
    member, _, _ = _member(
        client_db,
        world,
        "hard-audit-member@example.com",
        ["action.read", "action.operate"],
    )
    row_before = _definition_row(definition_id)
    audit_before = _definition_audit(world["workspace_id"])
    denied_create = client_db.post(
        f"{ACTIONS}/definitions",
        headers=member,
        json={"key": "member_made", "name": "Member made"},
    )
    denied_patch = client_db.patch(
        f"{ACTIONS}/definitions/{definition_id}",
        headers=member,
        json={"is_active": True},
    )
    assert denied_create.status_code == denied_patch.status_code == 403
    assert _definition_row(definition_id) == row_before
    assert _definition_audit(world["workspace_id"]) == audit_before

    admin, _, admin_id = _member(
        client_db, world, "hard-audit-admin@example.com", [], WorkspaceRole.ADMIN
    )
    by_admin = client_db.patch(
        f"{ACTIONS}/definitions/{definition_id}",
        headers=admin,
        json={"is_active": True},
    )
    assert by_admin.status_code == 200, by_admin.text
    last = _definition_audit(world["workspace_id"])[-1]
    assert last["actor"] == admin_id
    assert last["metadata"] == {"changed_fields": ["is_active"]}


def test_linking_guest_records_needs_their_read_capability(client_db):
    world = _world(client_db, "hard-link-owner@example.com")
    other_owner, other_token = register_verify_and_login(
        client_db, email="hard-link-other@example.com"
    )
    foreign_customer = _customer(client_db, other_token, "Foreign Guest")["id"]
    member, membership_id, _ = _member(
        client_db,
        world,
        "hard-link-member@example.com",
        ["action.read", "action.operate"],
    )
    missing = str(uuid.uuid4())
    before = _state(world["workspace_id"])

    def create(path, **links):
        body = {"action_definition_id": world["definition"], **links}
        if path == ACTIONS:
            body["payload"] = {"guest_phone": SECRET_PHONE}
        else:
            body["fields"] = {"guest_phone": SECRET_PHONE}
        return client_db.post(path, headers=member, json=body)

    for path in (ACTIONS, COLLECTIONS):
        bodies = set()
        for customer_id in (world["customer"], missing, foreign_customer):
            response = create(path, customer_id=customer_id)
            assert response.status_code == 403, response.text
            assert "guest.read" in response.json()["message"]
            bodies.add(response.text)
        # Real, missing and foreign ids are indistinguishable.
        assert len(bodies) == 1
        bodies = set()
        for conversation_id in (world["conversation"], missing):
            response = create(path, conversation_id=conversation_id)
            assert response.status_code == 403, response.text
            assert "conversation.read" in response.json()["message"]
            bodies.add(response.text)
        assert len(bodies) == 1
    assert _state(world["workspace_id"]) == before

    _grant(
        client_db,
        world,
        membership_id,
        ["action.read", "action.operate", "guest.read", "conversation.read"],
    )
    linked = create(
        ACTIONS, customer_id=world["customer"], conversation_id=world["conversation"]
    )
    assert linked.status_code == 201, linked.text
    for customer_id in (missing, foreign_customer):
        response = create(ACTIONS, customer_id=customer_id)
        assert response.status_code == 404, response.text
        assert "Foreign Guest" not in response.text
    assert other_owner["workspace"]["id"] not in linked.text


def _webchat_state(workspace_id):
    async def read():
        async with TestSessionLocal() as session:
            scope = uuid.UUID(workspace_id)

            async def count(model):
                return await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.workspace_id == scope)
                )

            collections = await session.execute(
                select(ActionCollectionSession.id, ActionCollectionSession.status)
                .where(ActionCollectionSession.workspace_id == scope)
                .order_by(ActionCollectionSession.id)
            )
            return (
                [tuple(row) for row in collections.all()],
                await count(ActionRequest),
                await count(Notification),
            )

    return asyncio.run(read())


def test_webchat_visitors_only_decide_their_own_collection(
    client_db, monkeypatch: pytest.MonkeyPatch
):
    _install_fake_grounded(monkeypatch)
    workspace_key, headers = _workspace(client_db, "hard-webchat@example.com")
    definition = client_db.post(
        f"{ACTIONS}/definitions",
        headers=headers,
        json={
            "key": "support_ticket",
            "name": "Support ticket",
            "required_fields": [
                {
                    "key": "subject",
                    "label": "Subject",
                    "type": "string",
                    "required": True,
                }
            ],
        },
    )
    assert definition.status_code == 201, definition.text
    workspace_id = definition.json()["data"]["workspace_id"]
    owner_chat = _session(client_db, workspace_key)
    neighbour_chat = _session(client_db, workspace_key)
    foreign_key, _ = _workspace(client_db, "hard-webchat-foreign@example.com")
    foreign_chat = _session(client_db, foreign_key)
    proposal = _send(
        client_db,
        owner_chat,
        "ticket-1",
        'action:support_ticket {"subject":"Room 101 key for +66899990001"}',
    )
    assert proposal.status_code == 201, proposal.text
    assistant = proposal.json()["data"]["assistant"]
    assert assistant["type"] == "ACTION_CONFIRMATION"
    collection_id = assistant["action_collection"]["session_id"]
    token = assistant["action_collection"]["confirmation_token"]
    before = _webchat_state(workspace_id)

    def decide(chat, conversation_id, decision):
        return client_db.post(
            f"/api/v1/webchat/sessions/{conversation_id}/action-collections/"
            f"{collection_id}/{decision}",
            headers={"X-WebChat-Token": chat["session_token"]},
            json={
                "client_message_id": f"{decision}-{uuid.uuid4().hex[:8]}",
                "confirmation_token": token,
            },
        )

    for chat in (neighbour_chat, foreign_chat):
        for decision in ("confirm", "cancel"):
            for conversation_id in (
                chat["conversation_id"],
                owner_chat["conversation_id"],
            ):
                response = decide(chat, conversation_id, decision)
                assert response.status_code == 401, response.text
                assert "+66899990001" not in response.text
                assert collection_id not in response.text
    assert _webchat_state(workspace_id) == before

    confirmed = decide(owner_chat, owner_chat["conversation_id"], "confirm")
    assert confirmed.status_code == 200, confirmed.text
    data = confirmed.json()["data"]
    assert data["type"] == "ACTION_CREATED"
    assert "+66899990001" not in confirmed.text

    async def created_action():
        async with TestSessionLocal() as session:
            return await session.get(
                ActionRequest, uuid.UUID(data["action_request_id"])
            )

    action = asyncio.run(created_action())
    # The visitor is not a Workspace user, so no user is credited.
    assert action.created_by_user_id is None
    assert str(action.conversation_id) == owner_chat["conversation_id"]
    collections, actions, _ = _webchat_state(workspace_id)
    assert actions == before[1] + 1
    assert dict(collections)[uuid.UUID(collection_id)].value == "CONFIRMED"
