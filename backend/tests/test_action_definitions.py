"""Action definition and payload validator coverage."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ActionPayloadValidationError
from app.models.action import ActionDefinition
from app.services.action_validation import ActionPayloadValidator
from tests.conftest import register_verify_and_login

URL = "/api/v1/actions/definitions"


def _auth(client, email):
    user, token = register_verify_and_login(client, email=email)
    return user["user"], {"Authorization": f"Bearer {token}"}


def _payload(key="top_up", active=True):
    return {
        "key": key,
        "name": "Top up",
        "execution_mode": "MANUAL",
        "is_active": active,
        "required_fields": [
            {"key": "name", "label": "Name", "type": "string", "required": True},
            {
                "key": "quantity",
                "label": "Quantity",
                "type": "integer",
                "required": True,
            },
            {"key": "amount", "label": "Amount", "type": "number", "required": True},
            {"key": "urgent", "label": "Urgent", "type": "boolean", "required": True},
            {
                "key": "package",
                "label": "Package",
                "type": "enum",
                "required": True,
                "values": ["A", "B"],
            },
        ],
        "optional_fields": [],
    }


def test_create_list_get_update_definition(client_db: TestClient) -> None:
    _, headers = _auth(client_db, "definitions@example.com")
    created = client_db.post(URL, headers=headers, json=_payload())
    assert created.status_code == 201
    definition_id = created.json()["data"]["id"]
    assert client_db.get(URL, headers=headers).json()["data"][0]["id"] == definition_id
    assert client_db.get(f"{URL}/{definition_id}", headers=headers).status_code == 200
    updated = client_db.patch(
        f"{URL}/{definition_id}", headers=headers, json={"is_active": False}
    )
    assert updated.json()["data"]["is_active"] is False


def test_duplicate_same_workspace_rejected_and_other_workspace_allowed(
    client_db: TestClient,
) -> None:
    _, first = _auth(client_db, "definition-one@example.com")
    _, second = _auth(client_db, "definition-two@example.com")
    assert client_db.post(URL, headers=first, json=_payload()).status_code == 201
    assert client_db.post(URL, headers=first, json=_payload()).status_code == 409
    assert client_db.post(URL, headers=second, json=_payload()).status_code == 201


def test_cross_workspace_definition_hidden(client_db: TestClient) -> None:
    _, first = _auth(client_db, "definition-owner@example.com")
    _, second = _auth(client_db, "definition-foreign@example.com")
    definition_id = client_db.post(URL, headers=first, json=_payload()).json()["data"][
        "id"
    ]
    assert client_db.get(f"{URL}/{definition_id}", headers=second).status_code == 404


def _definition():
    return ActionDefinition(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        key="test",
        name="Test",
        execution_mode="MANUAL",
        required_fields=_payload()["required_fields"],
        optional_fields=[],
        is_active=True,
    )


def test_payload_validator_accepts_all_supported_types_and_normalizes_string() -> None:
    value = {
        "name": "  Alice  ",
        "quantity": 2,
        "amount": 4.5,
        "urgent": False,
        "package": "A",
    }
    assert ActionPayloadValidator().validate(_definition(), value)["name"] == "Alice"


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({}, "missing_fields"),
        (
            {"name": 1, "quantity": "2", "amount": True, "urgent": 1, "package": "Z"},
            "invalid_fields",
        ),
        (
            {
                "name": "A",
                "quantity": 1,
                "amount": 1,
                "urgent": True,
                "package": "A",
                "unknown": 1,
            },
            "unknown_fields",
        ),
        (
            {
                "name": "A",
                "quantity": 1,
                "amount": 1,
                "urgent": True,
                "package": "A",
                "status": "COMPLETED",
            },
            "unknown_fields",
        ),
    ],
)
def test_payload_validator_rejects_invalid_missing_unknown_and_system_fields(
    payload, detail
) -> None:
    with pytest.raises(ActionPayloadValidationError) as captured:
        ActionPayloadValidator().validate(_definition(), payload)
    assert detail in captured.value.details
