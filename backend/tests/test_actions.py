"""PostgreSQL-backed fulfillment queue lifecycle and isolation tests."""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.action import ActionEvent
from tests.conftest import TestSessionLocal, register_verify_and_login

URL = "/api/v1/actions"


def _auth(client, email):
    user, token = register_verify_and_login(client, email=email)
    return user["user"], {"Authorization": f"Bearer {token}"}


def _definition(client, headers, active=True):
    response = client.post(
        f"{URL}/definitions",
        headers=headers,
        json={
            "key": "callback",
            "name": "Customer callback",
            "is_active": active,
            "required_fields": [
                {"key": "phone", "label": "Phone", "type": "string", "required": True}
            ],
            "optional_fields": [],
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _create(client, headers, definition_id, **extra):
    payload = {"action_definition_id": definition_id, "payload": {"phone": "123"}}
    payload.update(extra)
    return client.post(URL, headers=headers, json=payload)


def test_manual_creation_defaults_idempotency_and_creation_event(
    client_db: TestClient,
) -> None:
    user, headers = _auth(client_db, "action-create@example.com")
    definition_id = _definition(client_db, headers)
    first = _create(client_db, headers, definition_id, idempotency_key="retry-1")
    second = _create(client_db, headers, definition_id, idempotency_key="retry-1")
    assert first.status_code == second.status_code == 201
    data = first.json()["data"]
    assert second.json()["data"]["id"] == data["id"]
    assert data["priority"] == "NORMAL" and data["created_by_type"] == "HUMAN"
    assert data["created_by_user_id"] == user["id"]

    async def inspect():
        async with TestSessionLocal() as session:
            events = list(
                (
                    await session.execute(
                        select(ActionEvent).where(
                            ActionEvent.action_request_id == uuid.UUID(data["id"])
                        )
                    )
                ).scalars()
            )
            assert [event.event_type.value for event in events] == ["CREATED"]
            assert events[0].event_metadata == {}

    asyncio.run(inspect())


def test_inactive_definition_and_missing_fields_do_not_create(
    client_db: TestClient,
) -> None:
    _, headers = _auth(client_db, "action-invalid@example.com")
    inactive = _definition(client_db, headers, active=False)
    assert _create(client_db, headers, inactive).status_code == 404
    active = client_db.patch(
        f"{URL}/definitions/{inactive}", headers=headers, json={"is_active": True}
    )
    assert active.status_code == 200
    response = client_db.post(
        URL, headers=headers, json={"action_definition_id": inactive, "payload": {}}
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["missing_fields"] == ["phone"]


def test_assignment_lifecycle_timestamps_and_audit_order(client_db: TestClient) -> None:
    user, headers = _auth(client_db, "action-flow@example.com")
    action_id = _create(client_db, headers, _definition(client_db, headers)).json()[
        "data"
    ]["id"]
    assigned = client_db.post(
        f"{URL}/{action_id}/assign", headers=headers, json={"user_id": user["id"]}
    )
    assert assigned.json()["data"]["status"] == "ASSIGNED"
    assert assigned.json()["data"]["assigned_at"] is not None
    started = client_db.post(f"{URL}/{action_id}/start", headers=headers)
    assert started.json()["data"]["started_at"] is not None
    completed = client_db.post(f"{URL}/{action_id}/complete", headers=headers)
    assert completed.json()["data"]["completed_at"] is not None
    assert (
        client_db.post(f"{URL}/{action_id}/start", headers=headers).status_code == 409
    )

    async def inspect():
        async with TestSessionLocal() as session:
            events = list(
                (
                    await session.execute(
                        select(ActionEvent)
                        .where(ActionEvent.action_request_id == uuid.UUID(action_id))
                        .order_by(ActionEvent.created_at, ActionEvent.id)
                    )
                ).scalars()
            )
            assert [event.event_type.value for event in events] == [
                "CREATED",
                "ASSIGNED",
                "STARTED",
                "COMPLETED",
            ]
            assert all("phone" not in event.event_metadata for event in events)

    asyncio.run(inspect())


def test_cancel_fail_and_invalid_transitions(client_db: TestClient) -> None:
    user, headers = _auth(client_db, "action-status@example.com")
    definition_id = _definition(client_db, headers)
    waiting = _create(client_db, headers, definition_id).json()["data"]["id"]
    assert (
        client_db.post(f"{URL}/{waiting}/cancel", headers=headers).json()["data"][
            "status"
        ]
        == "CANCELLED"
    )
    action_id = _create(client_db, headers, definition_id).json()["data"]["id"]
    client_db.post(
        f"{URL}/{action_id}/assign", headers=headers, json={"user_id": user["id"]}
    )
    client_db.post(f"{URL}/{action_id}/start", headers=headers)
    assert (
        client_db.post(f"{URL}/{action_id}/fail", headers=headers).json()["data"][
            "status"
        ]
        == "FAILED"
    )


def test_workspace_isolation_foreign_assignment_and_idempotency_scope(
    client_db: TestClient,
) -> None:
    first_user, first = _auth(client_db, "action-first@example.com")
    second_user, second = _auth(client_db, "action-second@example.com")
    first_definition = _definition(client_db, first)
    second_definition = _definition(client_db, second)
    first_action = _create(
        client_db, first, first_definition, idempotency_key="shared"
    ).json()["data"]["id"]
    second_action = _create(
        client_db, second, second_definition, idempotency_key="shared"
    ).json()["data"]["id"]
    assert first_action != second_action
    assert client_db.get(f"{URL}/{first_action}", headers=second).status_code == 404
    assert (
        client_db.post(
            f"{URL}/{first_action}/assign",
            headers=first,
            json={"user_id": second_user["id"]},
        ).status_code
        == 422
    )
    assert (
        client_db.post(
            f"{URL}/{first_action}/assign",
            headers=first,
            json={"user_id": first_user["id"]},
        ).status_code
        == 200
    )


def test_queue_filters_pagination_order_and_auth(client_db: TestClient) -> None:
    user, headers = _auth(client_db, "action-list@example.com")
    definition_id = _definition(client_db, headers)
    first = _create(client_db, headers, definition_id, priority="HIGH").json()["data"]
    second = _create(client_db, headers, definition_id).json()["data"]
    client_db.post(
        f"{URL}/{second['id']}/assign", headers=headers, json={"user_id": user["id"]}
    )
    assert client_db.get(URL).status_code == 401
    high = client_db.get(URL, headers=headers, params={"priority": "HIGH"}).json()[
        "data"
    ]
    assert [item["id"] for item in high["items"]] == [first["id"]]
    assigned = client_db.get(
        URL,
        headers=headers,
        params={
            "status": "ASSIGNED",
            "assigned_to": user["id"],
            "action_definition_id": definition_id,
            "page": 1,
            "page_size": 1,
        },
    ).json()["data"]
    assert assigned["total"] == 1 and assigned["items"][0]["id"] == second["id"]
