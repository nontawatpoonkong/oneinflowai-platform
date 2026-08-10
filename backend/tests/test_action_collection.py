"""PostgreSQL-backed action collection, confirmation, and isolation tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.services.action_collection as collection_service_module
from app.models.action import ActionRequest
from app.models.action_collection import (
    ActionCollectionSession,
    ActionCollectionStatus,
)
from tests.conftest import TestSessionLocal, register_verify_and_login

URL = "/api/v1/action-collections"


def _auth(client, email):
    _, token = register_verify_and_login(client, email=email)
    return token, {"Authorization": f"Bearer {token}"}


def _definition(client, headers, *, active=True):
    response = client.post(
        "/api/v1/actions/definitions",
        headers=headers,
        json={
            "key": f"topup_{uuid.uuid4().hex[:8]}",
            "name": "Game Top-up",
            "is_active": active,
            "required_fields": [
                {
                    "key": "server",
                    "label": "Server",
                    "type": "enum",
                    "required": True,
                    "values": ["Asia", "EU"],
                },
                {
                    "key": "account",
                    "label": "Account ID",
                    "type": "string",
                    "required": True,
                },
            ],
            "optional_fields": [
                {
                    "key": "note",
                    "label": "รายละเอียด",
                    "type": "string",
                    "required": False,
                }
            ],
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _create(client, headers, definition_id, **extra):
    body = {"action_definition_id": definition_id}
    body.update(extra)
    return client.post(URL, headers=headers, json=body)


def _inspect(session_id):
    async def inspect():
        async with TestSessionLocal() as session:
            return await session.get(ActionCollectionSession, uuid.UUID(session_id))

    return asyncio.run(inspect())


def test_session_collects_multiturn_fields_and_returns_safe_metadata(
    client_db: TestClient,
) -> None:
    _, headers = _auth(client_db, "collection-multiturn@example.com")
    definition_id = _definition(client_db, headers)
    created = _create(
        client_db,
        headers,
        definition_id,
        fields={"account": "  Non#TH1  ", "note": "ส่งของที่ไทย"},
        workspace_id=str(uuid.uuid4()),
        status="CONFIRMED",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["session"]["status"] == "COLLECTING"
    assert data["session"]["collected_payload"] == {
        "account": "Non#TH1",
        "note": "ส่งของที่ไทย",
    }
    assert data["session"]["missing_fields"] == ["server"]
    assert data["missing_field_metadata"] == [
        {"key": "server", "label": "Server", "type": "enum"}
    ]
    completed = client_db.post(
        f"{URL}/{data['session']['id']}/input",
        headers=headers,
        json={"fields": {"server": "Asia"}},
    ).json()["data"]
    assert completed["session"]["status"] == "AWAITING_CONFIRMATION"
    assert completed["session"]["collected_payload"]["account"] == "Non#TH1"
    assert completed["confirmation_token"]
    assert completed["confirmation_summary"]["fields"] == [
        {"key": "server", "label": "Server", "value": "Asia"},
        {"key": "account", "label": "Account ID", "value": "Non#TH1"},
        {"key": "note", "label": "รายละเอียด", "value": "ส่งของที่ไทย"},
    ]
    fetched = client_db.get(f"{URL}/{data['session']['id']}", headers=headers).json()[
        "data"
    ]
    assert fetched["confirmation_summary"] == completed["confirmation_summary"]
    assert fetched["confirmation_token"] is None
    stored = _inspect(data["session"]["id"])
    assert stored.confirmation_token_hash != completed["confirmation_token"]
    assert len(stored.confirmation_token_hash) == 64


def test_invalid_unknown_and_system_fields_never_enter_payload(
    client_db: TestClient,
) -> None:
    _, headers = _auth(client_db, "collection-invalid@example.com")
    definition_id = _definition(client_db, headers)
    invalid = _create(
        client_db,
        headers,
        definition_id,
        fields={"server": "Mars", "account": "A"},
    )
    assert invalid.status_code == 201
    assert invalid.json()["data"]["session"]["invalid_fields"] == {
        "server": "unsupported enum value"
    }
    for injected in ({"unknown": "x"}, {"status": "CONFIRMED"}):
        response = _create(
            client_db, headers, definition_id, fields={"account": "A", **injected}
        )
        assert response.status_code == 422
        assert (
            list(injected)[0] in response.json()["error"]["details"]["unknown_fields"]
        )


def test_development_provider_candidates_are_untrusted_and_validated(
    client_db: TestClient,
) -> None:
    _, headers = _auth(client_db, "collection-provider@example.com")
    definition_id = _definition(client_db, headers)
    valid = _create(
        client_db,
        headers,
        definition_id,
        initial_input='{"server":"Asia","account":"ผู้เล่น One#TH"}',
    )
    assert valid.status_code == 201
    assert valid.json()["data"]["session"]["status"] == "AWAITING_CONFIRMATION"
    invented = _create(
        client_db,
        headers,
        definition_id,
        initial_input='{"server":"Asia","account":"A","priority":"URGENT"}',
    )
    assert invented.status_code == 422
    malformed = _create(client_db, headers, definition_id, initial_input="raw secret")
    assert malformed.status_code == 502
    assert "raw secret" not in malformed.text


def test_definition_workspace_and_authentication_are_enforced(
    client_db: TestClient,
) -> None:
    _, first = _auth(client_db, "collection-first@example.com")
    _, second = _auth(client_db, "collection-second@example.com")
    active = _definition(client_db, first)
    inactive = _definition(client_db, first, active=False)
    assert _create(client_db, {}, active).status_code == 401
    assert _create(client_db, second, active).status_code == 404
    assert _create(client_db, first, inactive).status_code == 404


def test_conversation_customer_ownership_and_consistency_enforced(
    client_db: TestClient,
) -> None:
    first_token, first = _auth(client_db, "collection-links-first@example.com")
    second_token, second = _auth(client_db, "collection-links-second@example.com")
    first_customer = client_db.post(
        "/api/v1/customers", headers=first, json={"display_name": "First"}
    ).json()["data"]["id"]
    other_customer = client_db.post(
        "/api/v1/customers", headers=first, json={"display_name": "Other"}
    ).json()["data"]["id"]
    foreign_customer = client_db.post(
        "/api/v1/customers", headers=second, json={"display_name": "Foreign"}
    ).json()["data"]["id"]
    conversation = client_db.post(
        "/api/v1/conversations",
        headers=first,
        json={"customer_id": first_customer, "channel": "web"},
    ).json()["data"]["id"]
    definition_id = _definition(client_db, first)
    assert (
        _create(
            client_db,
            first,
            definition_id,
            conversation_id=conversation,
            customer_id=first_customer,
        ).status_code
        == 201
    )
    assert (
        _create(
            client_db,
            first,
            definition_id,
            conversation_id=conversation,
            customer_id=other_customer,
        ).status_code
        == 422
    )
    assert (
        _create(
            client_db, first, definition_id, customer_id=foreign_customer
        ).status_code
        == 404
    )
    assert first_token != second_token


def test_payload_change_invalidates_old_confirmation_token(
    client_db: TestClient,
) -> None:
    _, headers = _auth(client_db, "collection-mutate@example.com")
    definition_id = _definition(client_db, headers)
    first = _create(
        client_db, headers, definition_id, fields={"server": "Asia", "account": "A"}
    ).json()["data"]
    session_id = first["session"]["id"]
    changed = client_db.post(
        f"{URL}/{session_id}/input",
        headers=headers,
        json={"fields": {"account": "B"}},
    ).json()["data"]
    assert changed["confirmation_token"] != first["confirmation_token"]
    assert (
        client_db.post(
            f"{URL}/{session_id}/confirm",
            headers=headers,
            json={"confirmation_token": first["confirmation_token"]},
        ).status_code
        == 401
    )


def test_explicit_confirmation_is_atomic_linked_and_idempotent(
    client_db: TestClient,
) -> None:
    token, headers = _auth(client_db, "collection-confirm@example.com")
    customer = client_db.post(
        "/api/v1/customers", headers=headers, json={"display_name": "Customer"}
    ).json()["data"]["id"]
    conversation = client_db.post(
        "/api/v1/conversations",
        headers=headers,
        json={"customer_id": customer, "channel": "web"},
    ).json()["data"]["id"]
    created = _create(
        client_db,
        headers,
        _definition(client_db, headers),
        customer_id=customer,
        conversation_id=conversation,
        fields={"server": "Asia", "account": "Non#TH1"},
    ).json()["data"]
    session_id = created["session"]["id"]
    body = {"confirmation_token": created["confirmation_token"]}
    first = client_db.post(f"{URL}/{session_id}/confirm", headers=headers, json=body)
    second = client_db.post(f"{URL}/{session_id}/confirm", headers=headers, json=body)
    assert first.status_code == second.status_code == 200
    action = first.json()["data"]["action"]
    assert second.json()["data"]["action"]["id"] == action["id"]
    assert action["payload"] == {"server": "Asia", "account": "Non#TH1"}
    assert (
        action["conversation_id"] == conversation and action["customer_id"] == customer
    )
    assert first.json()["data"]["confirmation_token"] is None
    assert first.json()["data"]["session"]["status"] == "CONFIRMED"
    assert token

    async def count_actions():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(func.count(ActionRequest.id)).where(
                    ActionRequest.id == uuid.UUID(action["id"])
                )
            )

    assert asyncio.run(count_actions()) == 1
    assert (
        client_db.post(f"{URL}/{session_id}/cancel", headers=headers).status_code == 409
    )


def test_action_creation_failure_does_not_falsely_confirm(
    client_db: TestClient, monkeypatch
) -> None:
    _, headers = _auth(client_db, "collection-atomic@example.com")
    created = _create(
        client_db,
        headers,
        _definition(client_db, headers),
        fields={"server": "Asia", "account": "A"},
    ).json()["data"]

    async def fail_create(*args, **kwargs):
        raise RuntimeError("forced action failure")

    monkeypatch.setattr(collection_service_module.ActionService, "create", fail_create)
    with pytest.raises(RuntimeError, match="forced action failure"):
        client_db.post(
            f"{URL}/{created['session']['id']}/confirm",
            headers=headers,
            json={"confirmation_token": created["confirmation_token"]},
        )
    assert (
        _inspect(created["session"]["id"]).status
        is ActionCollectionStatus.AWAITING_CONFIRMATION
    )


def test_expiration_cancel_and_cross_workspace_get_are_safe(
    client_db: TestClient,
) -> None:
    _, first = _auth(client_db, "collection-state-first@example.com")
    _, second = _auth(client_db, "collection-state-second@example.com")
    created = _create(client_db, first, _definition(client_db, first)).json()["data"]
    session_id = created["session"]["id"]
    assert client_db.get(f"{URL}/{session_id}", headers=second).status_code == 404
    cancelled = client_db.post(f"{URL}/{session_id}/cancel", headers=first)
    assert cancelled.json()["data"]["session"]["status"] == "CANCELLED"

    token_expiring = _create(
        client_db,
        first,
        _definition(client_db, first),
        fields={"server": "Asia", "account": "A"},
    ).json()["data"]

    async def expire_confirmation():
        async with TestSessionLocal() as session:
            value = await session.get(
                ActionCollectionSession,
                uuid.UUID(token_expiring["session"]["id"]),
            )
            value.confirmation_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_confirmation())
    token_expired = client_db.post(
        f"{URL}/{token_expiring['session']['id']}/confirm",
        headers=first,
        json={"confirmation_token": token_expiring["confirmation_token"]},
    )
    assert token_expired.status_code == 401
    assert (
        _inspect(token_expiring["session"]["id"]).status
        is ActionCollectionStatus.AWAITING_CONFIRMATION
    )

    expiring = _create(
        client_db,
        first,
        _definition(client_db, first),
        fields={"server": "Asia", "account": "A"},
    ).json()["data"]

    async def expire():
        async with TestSessionLocal() as session:
            value = await session.get(
                ActionCollectionSession, uuid.UUID(expiring["session"]["id"])
            )
            value.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire())
    response = client_db.post(
        f"{URL}/{expiring['session']['id']}/confirm",
        headers=first,
        json={"confirmation_token": expiring["confirmation_token"]},
    )
    assert response.status_code == 409
    assert _inspect(expiring["session"]["id"]).status is ActionCollectionStatus.EXPIRED
