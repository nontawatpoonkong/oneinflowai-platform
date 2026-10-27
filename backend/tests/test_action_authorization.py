"""F4: Actions, Action Collections, availability and quotes need capabilities.

action.read covers reading Actions, Action Definitions and Action Collections.
action.operate covers creating Actions and every Action state change. Action
responses carry guest data (payload, customer and conversation links) only for
callers who also hold action.read. Collection changes return collected guest
data and a confirmation summary, so they need action.operate and action.read.
Action Definition changes stay OWNER/ADMIN-only. Availability search and
quotes need room.read. Denials write nothing and send no notification.
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.models.action import ActionEvent, ActionRequest
from app.models.action_collection import ActionCollectionSession
from app.models.audit import WorkspaceAuditEvent
from app.models.booking import Booking
from app.models.hotel import InventoryDate
from app.models.notification import Notification
from app.models.workspace_access import (
    WorkspaceAccessRequest,
    WorkspaceMemberCapability,
)
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_booking import _setup
from tests.test_crm import _conversation, _customer
from tests.test_hotel import _auth
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

ACTIONS = "/api/v1/actions"
COLLECTIONS = "/api/v1/action-collections"
SECRET_PHONE = "+66899990001"
SECRET_KEY = "f4-secret-idempotency"
OPERATOR_FIELDS = {
    "id",
    "workspace_id",
    "action_definition_id",
    "status",
    "priority",
    "created_by_type",
    "created_by_user_id",
    "assigned_to_user_id",
    "assigned_at",
    "started_at",
    "completed_at",
    "cancelled_at",
    "created_at",
    "updated_at",
    "details_visible",
}


def _world(client, email):
    """Owner Workspace with a definition, a guest-linked Action and a Collection."""

    owner, token = register_verify_and_login(client, email=email)
    workspace_id = owner["workspace"]["id"]
    definition = client.post(
        f"{ACTIONS}/definitions",
        headers=_auth(token),
        json={
            "key": "guest_callback",
            "name": "Guest callback",
            "required_fields": [
                {
                    "key": "guest_phone",
                    "label": "Guest phone",
                    "type": "string",
                    "required": True,
                }
            ],
            "optional_fields": [],
        },
    )
    assert definition.status_code == 201, definition.text
    definition_id = definition.json()["data"]["id"]
    customer = _customer(client, token)
    conversation_id = _conversation(client, token, customer["id"])
    action = client.post(
        ACTIONS,
        headers=_auth(token),
        json={
            "action_definition_id": definition_id,
            "customer_id": customer["id"],
            "conversation_id": conversation_id,
            "payload": {"guest_phone": SECRET_PHONE},
            "idempotency_key": SECRET_KEY,
        },
    )
    assert action.status_code == 201, action.text
    collection = client.post(
        COLLECTIONS,
        headers=_auth(token),
        json={
            "action_definition_id": definition_id,
            "customer_id": customer["id"],
            "fields": {"guest_phone": SECRET_PHONE},
        },
    )
    assert collection.status_code == 201, collection.text
    collection_data = collection.json()["data"]
    assert collection_data["next_step"] == "CONFIRM_ACTION"
    return {
        "owner": owner,
        "token": token,
        "workspace_id": workspace_id,
        "definition": definition_id,
        "customer": customer["id"],
        "conversation": conversation_id,
        "action": action.json()["data"]["id"],
        "collection": collection_data["session"]["id"],
        "confirmation_token": collection_data["confirmation_token"],
    }


def _member(client, world, email, capabilities, role=WorkspaceRole.MEMBER):
    user, token = _zero_workspace_account(client, email)
    membership_id = _add_member(world["workspace_id"], user["id"], role)
    if role is WorkspaceRole.MEMBER:
        _grant(client, world, membership_id, capabilities)
    return _headers(token, world["workspace_id"]), membership_id, user["id"]


def _grant(client, world, membership_id, capabilities):
    granted = client.put(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}/capabilities",
        headers=_headers(world["token"]),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text


def _state(workspace_id):
    """Every row a denied action request could plausibly change."""

    async def read():
        async with TestSessionLocal() as session:
            scope = uuid.UUID(workspace_id)

            async def rows(model, *columns):
                result = await session.execute(
                    select(*columns)
                    .where(model.workspace_id == scope)
                    .order_by(*columns)
                )
                return [tuple(row) for row in result.all()]

            return {
                "actions": await rows(
                    ActionRequest,
                    ActionRequest.id,
                    ActionRequest.status,
                    ActionRequest.assigned_to_user_id,
                    ActionRequest.updated_at,
                ),
                "events": await rows(ActionEvent, ActionEvent.id),
                "collections": await rows(
                    ActionCollectionSession,
                    ActionCollectionSession.id,
                    ActionCollectionSession.status,
                    ActionCollectionSession.updated_at,
                ),
                "notifications": await rows(Notification, Notification.id),
                "members": await rows(
                    WorkspaceMember, WorkspaceMember.id, WorkspaceMember.role
                ),
                "grants": await rows(
                    WorkspaceMemberCapability,
                    WorkspaceMemberCapability.membership_id,
                    WorkspaceMemberCapability.capability,
                ),
                "join_requests": await rows(
                    WorkspaceAccessRequest,
                    WorkspaceAccessRequest.id,
                    WorkspaceAccessRequest.status,
                ),
                "audit": await rows(WorkspaceAuditEvent, WorkspaceAuditEvent.id),
                "bookings": await rows(Booking, Booking.id),
                "inventory": await rows(
                    InventoryDate, InventoryDate.id, InventoryDate.reserved_units
                ),
            }

    return asyncio.run(read())


def _secrets(world):
    return (
        SECRET_PHONE,
        SECRET_KEY,
        world["customer"],
        world["conversation"],
        world["confirmation_token"],
    )


def _assert_no_secrets(response, world):
    for value in _secrets(world):
        assert value not in response.text, value


def _read_requests(world):
    return [
        ("get", ACTIONS, None),
        ("get", f"{ACTIONS}/{world['action']}", None),
        ("get", f"{ACTIONS}/definitions", None),
        ("get", f"{ACTIONS}/definitions/{world['definition']}", None),
        ("get", f"{COLLECTIONS}/{world['collection']}", None),
    ]


def _operate_requests(world, assignee_id):
    action = f"{ACTIONS}/{world['action']}"
    return [
        (
            "post",
            ACTIONS,
            {
                "action_definition_id": world["definition"],
                "customer_id": world["customer"],
                "payload": {"guest_phone": SECRET_PHONE},
            },
        ),
        ("post", f"{action}/assign", {"user_id": assignee_id}),
        ("post", f"{action}/start", None),
        ("post", f"{action}/complete", None),
        ("post", f"{action}/fail", None),
        ("post", f"{action}/cancel", None),
    ]


def _collection_requests(world):
    collection = f"{COLLECTIONS}/{world['collection']}"
    return [
        (
            "post",
            COLLECTIONS,
            {
                "action_definition_id": world["definition"],
                "fields": {"guest_phone": SECRET_PHONE},
            },
        ),
        ("post", f"{collection}/input", {"fields": {"guest_phone": "+66800000000"}}),
        (
            "post",
            f"{collection}/confirm",
            {"confirmation_token": world["confirmation_token"]},
        ),
        ("post", f"{collection}/cancel", None),
    ]


def _send(client, method, path, body, headers):
    if body is None:
        return getattr(client, method)(path, headers=headers)
    return getattr(client, method)(path, headers=headers, json=body)


def _assert_denied(client, world, headers, requests, capability):
    for method, path, body in requests:
        response = _send(client, method, path, body, headers)
        assert response.status_code == 403, (path, response.text)
        payload = response.json()
        assert payload["error"]["code"] == "FORBIDDEN", path
        assert capability in payload["message"], path
        assert payload["data"] is None
        _assert_no_secrets(response, world)


def _assert_operator_view(data, world):
    assert set(data) == OPERATOR_FIELDS
    assert data["details_visible"] is False
    for key in ("payload", "customer_id", "conversation_id", "idempotency_key"):
        assert key not in data


def test_dashboard_view_member_is_denied_reads_and_operations(client_db):
    world = _world(client_db, "f4-dashboard-owner@example.com")
    member, _, member_id = _member(
        client_db, world, "f4-dashboard-member@example.com", []
    )
    before = _state(world["workspace_id"])
    _assert_denied(client_db, world, member, _read_requests(world), "action.read")
    _assert_denied(
        client_db,
        world,
        member,
        _operate_requests(world, member_id),
        "action.operate",
    )
    _assert_denied(
        client_db, world, member, _collection_requests(world), "action.operate"
    )
    assert _state(world["workspace_id"]) == before


def test_action_read_member_reads_but_cannot_operate(client_db):
    world = _world(client_db, "f4-reader-owner@example.com")
    member, _, member_id = _member(
        client_db, world, "f4-reader@example.com", ["action.read"]
    )
    before = _state(world["workspace_id"])
    listing = client_db.get(ACTIONS, headers=member)
    assert listing.status_code == 200, listing.text
    [item] = listing.json()["data"]["items"]
    assert item["id"] == world["action"]
    assert item["payload"] == {"guest_phone": SECRET_PHONE}
    assert item["customer_id"] == world["customer"]
    detail = client_db.get(f"{ACTIONS}/{world['action']}", headers=member)
    assert detail.json()["data"]["conversation_id"] == world["conversation"]
    definitions = client_db.get(f"{ACTIONS}/definitions", headers=member)
    assert [item["id"] for item in definitions.json()["data"]] == [world["definition"]]
    collection = client_db.get(f"{COLLECTIONS}/{world['collection']}", headers=member)
    assert collection.status_code == 200, collection.text
    assert collection.json()["data"]["session"]["collected_payload"] == {
        "guest_phone": SECRET_PHONE
    }
    _assert_denied(
        client_db,
        world,
        member,
        _operate_requests(world, member_id),
        "action.operate",
    )
    _assert_denied(
        client_db, world, member, _collection_requests(world), "action.operate"
    )
    assert _state(world["workspace_id"]) == before


def test_action_operate_member_cannot_read_guest_data_through_responses(client_db):
    world = _world(client_db, "f4-operator-owner@example.com")
    member, _, _ = _member(
        client_db, world, "f4-operator@example.com", ["action.operate"]
    )
    _assert_denied(client_db, world, member, _read_requests(world), "action.read")
    collections_before = _state(world["workspace_id"])["collections"]
    # Collection changes return collected guest data, so they need action.read.
    _assert_denied(client_db, world, member, _collection_requests(world), "action.read")
    assert _state(world["workspace_id"])["collections"] == collections_before

    created = client_db.post(
        ACTIONS,
        headers=member,
        # Linking a customer or conversation also needs guest.read or
        # conversation.read (see test_action_hardening.py).
        json={
            "action_definition_id": world["definition"],
            "payload": {"guest_phone": SECRET_PHONE},
            "idempotency_key": "operator-create",
        },
    )
    assert created.status_code == 201, created.text
    _assert_operator_view(created.json()["data"], world)
    _assert_no_secrets(created, world)
    assert "operator-create" not in created.text
    # Assignees must hold action.read and action.operate, so assign the owner.
    for path, body, status in (
        ("assign", {"user_id": world["owner"]["user"]["id"]}, "ASSIGNED"),
        ("start", None, "IN_PROGRESS"),
        ("complete", None, "COMPLETED"),
    ):
        response = _send(
            client_db, "post", f"{ACTIONS}/{world['action']}/{path}", body, member
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        _assert_operator_view(data, world)
        assert data["status"] == status
        _assert_no_secrets(response, world)

    async def stored():
        async with TestSessionLocal() as session:
            action = await session.get(
                ActionRequest, uuid.UUID(created.json()["data"]["id"])
            )
            return action.payload, action.customer_id

    # The operation itself kept the full payload.
    assert asyncio.run(stored()) == ({"guest_phone": SECRET_PHONE}, None)


def test_member_with_both_capabilities_operates_per_policy(client_db):
    world = _world(client_db, "f4-both-owner@example.com")
    member, _, member_id = _member(
        client_db, world, "f4-both@example.com", ["action.read", "action.operate"]
    )
    for path, body in (
        ("assign", {"user_id": member_id}),
        ("start", None),
        ("complete", None),
    ):
        response = _send(
            client_db, "post", f"{ACTIONS}/{world['action']}/{path}", body, member
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["details_visible"] is True
        assert data["payload"] == {"guest_phone": SECRET_PHONE}
        assert data["customer_id"] == world["customer"]
    confirmed = client_db.post(
        f"{COLLECTIONS}/{world['collection']}/confirm",
        headers=member,
        json={"confirmation_token": world["confirmation_token"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    confirmed_data = confirmed.json()["data"]
    assert confirmed_data["next_step"] == "ACTION_CREATED"
    assert confirmed_data["action"]["payload"] == {"guest_phone": SECRET_PHONE}
    # Definitions stay OWNER/ADMIN-only even with both action capabilities.
    before = _state(world["workspace_id"])
    _assert_denied(
        client_db,
        world,
        member,
        [
            ("post", f"{ACTIONS}/definitions", {"key": "member_made", "name": "X"}),
            (
                "patch",
                f"{ACTIONS}/definitions/{world['definition']}",
                {"is_active": False},
            ),
        ],
        "",
    )
    definition = client_db.get(
        f"{ACTIONS}/definitions/{world['definition']}", headers=member
    ).json()["data"]
    assert definition["is_active"] is True
    assert _state(world["workspace_id"]) == before


def test_owner_and_admin_use_role_baseline(client_db):
    world = _world(client_db, "f4-baseline-owner@example.com")
    admin, _, admin_id = _member(
        client_db, world, "f4-admin@example.com", [], role=WorkspaceRole.ADMIN
    )
    for headers in (_auth(world["token"]), admin):
        listing = client_db.get(ACTIONS, headers=headers)
        assert listing.status_code == 200, listing.text
        assert listing.json()["data"]["items"][0]["payload"] == {
            "guest_phone": SECRET_PHONE
        }
        assert (
            client_db.get(
                f"{COLLECTIONS}/{world['collection']}", headers=headers
            ).status_code
            == 200
        )
    assigned = client_db.post(
        f"{ACTIONS}/{world['action']}/assign", headers=admin, json={"user_id": admin_id}
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["data"]["details_visible"] is True
    created = client_db.post(
        f"{ACTIONS}/definitions",
        headers=admin,
        json={"key": "admin_made", "name": "Admin made"},
    )
    assert created.status_code == 201, created.text


def test_revoked_grant_denies_the_next_request(client_db):
    world = _world(client_db, "f4-revoke-owner@example.com")
    member, membership_id, member_id = _member(
        client_db, world, "f4-revoked@example.com", ["action.read", "action.operate"]
    )
    assert client_db.get(ACTIONS, headers=member).status_code == 200
    _grant(client_db, world, membership_id, ["action.read"])
    before = _state(world["workspace_id"])
    _assert_denied(
        client_db,
        world,
        member,
        _operate_requests(world, member_id),
        "action.operate",
    )
    assert _state(world["workspace_id"]) == before
    _grant(client_db, world, membership_id, [])
    _assert_denied(client_db, world, member, _read_requests(world), "action.read")


def test_cross_workspace_ids_reveal_nothing(client_db):
    world = _world(client_db, "f4-tenant-a@example.com")
    other_user, other_token = register_verify_and_login(
        client_db, email="f4-tenant-b@example.com"
    )
    other = _auth(other_token)
    before = _state(world["workspace_id"])
    for method, path, body in (
        ("get", f"{ACTIONS}/{world['action']}", None),
        ("get", f"{ACTIONS}/definitions/{world['definition']}", None),
        ("get", f"{COLLECTIONS}/{world['collection']}", None),
        # The assignee belongs to the caller's Workspace, so only the foreign
        # Action id can fail.
        *_operate_requests(world, other_user["user"]["id"])[1:],
        *_collection_requests(world)[1:],
    ):
        response = _send(client_db, method, path, body, other)
        assert response.status_code == 404, (path, response.text)
        _assert_no_secrets(response, world)
    listing = client_db.get(ACTIONS, headers=other)
    assert listing.json()["data"]["items"] == []
    forged = client_db.get(
        f"{ACTIONS}/{world['action']}",
        headers={**other, "X-Workspace-ID": world["workspace_id"]},
    )
    assert forged.status_code == 403, forged.text
    _assert_no_secrets(forged, world)
    assert _state(world["workspace_id"]) == before


def test_transitions_are_idempotent_safe_and_serialised(client_db):
    world = _world(client_db, "f4-race-owner@example.com")
    member, _, member_id = _member(
        client_db, world, "f4-racer@example.com", ["action.read", "action.operate"]
    )
    # Replaying an idempotency key returns the same Action and notifies once.
    body = {
        "action_definition_id": world["definition"],
        "payload": {"guest_phone": SECRET_PHONE},
        "idempotency_key": "replayed",
    }
    first = client_db.post(ACTIONS, headers=member, json=body)
    replay = client_db.post(ACTIONS, headers=member, json=body)
    assert first.status_code == replay.status_code == 201
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    assigned = client_db.post(
        f"{ACTIONS}/{world['action']}/assign",
        headers=member,
        json={"user_id": member_id},
    )
    assert assigned.status_code == 200, assigned.text
    again = client_db.post(
        f"{ACTIONS}/{world['action']}/assign",
        headers=member,
        json={"user_id": member_id},
    )
    assert again.status_code == 409, again.text

    def start():
        return client_db.post(f"{ACTIONS}/{world['action']}/start", headers=member)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: start(), range(6)))
    assert sorted(response.status_code for response in results) == [200] + [409] * 5

    async def counts():
        async with TestSessionLocal() as session:
            action_id = uuid.UUID(world["action"])
            events = await session.scalars(
                select(ActionEvent.event_type).where(
                    ActionEvent.action_request_id == action_id
                )
            )
            notifications = await session.execute(
                select(Notification.type, func.count())
                .where(
                    Notification.entity_id.in_(
                        [action_id, uuid.UUID(first.json()["data"]["id"])]
                    )
                )
                .group_by(Notification.type)
            )
            return sorted(item.value for item in events), {
                row[0].value: row[1] for row in notifications.all()
            }

    events, notifications = asyncio.run(counts())
    assert events == ["ASSIGNED", "CREATED", "STARTED"]
    # One assignment notice; creation notices go once per admin recipient for
    # each of the two Actions (the owner is the only admin here).
    assert notifications == {"ACTION_ASSIGNED": 1, "ACTION_CREATED": 2}


def test_availability_and_quotes_need_room_read_and_write_nothing(client_db):
    owner, token, prop, room, plan = _setup(
        client_db, email="f4-room-owner@example.com"
    )
    world = {
        "workspace_id": owner["workspace"]["id"],
        "token": token,
    }
    search = {
        "property_id": prop["id"],
        "check_in": "2030-01-01",
        "check_out": "2030-01-04",
        "adults": 2,
        "children": 0,
    }
    quote = {**search, "rate_plan_id": plan["id"]}
    denied, _, _ = _member(client_db, world, "f4-no-room@example.com", [])
    reader, _, _ = _member(
        client_db, world, "f4-room-reader@example.com", ["room.read"]
    )
    before = _state(world["workspace_id"])
    for path, body in (
        ("/api/v1/hotel/availability/search", search),
        ("/api/v1/hotel/quotes", quote),
    ):
        response = client_db.post(path, headers=denied, json=body)
        assert response.status_code == 403, response.text
        assert "room.read" in response.json()["message"]
        assert plan["id"] not in response.text and room["id"] not in response.text
        for headers in (reader, _auth(token)):
            allowed = client_db.post(path, headers=headers, json=body)
            assert allowed.status_code == 200, allowed.text
            [result] = allowed.json()["data"]["results"]
            assert result["rate_plan_id"] == plan["id"]
            assert result["available_units"] == 1
    assert _state(world["workspace_id"]) == before
