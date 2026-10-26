"""Action definition and payload validator coverage."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.exceptions import ActionPayloadValidationError
from app.models.action import ActionDefinition
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.action_validation import ActionPayloadValidator
from tests.conftest import TestSessionLocal, register_verify_and_login

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


def _set_role(user_id: str, role: WorkspaceRole) -> None:
    async def _update() -> None:
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.user_id == uuid.UUID(user_id)
                )
            )
            assert membership is not None
            membership.role = role
            await session.commit()

    asyncio.run(_update())


def _grant(user_id: str, *capabilities: str) -> None:
    async def _insert() -> None:
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.user_id == uuid.UUID(user_id)
                )
            )
            for capability in capabilities:
                session.add(
                    WorkspaceMemberCapability(
                        workspace_id=membership.workspace_id,
                        membership_id=membership.id,
                        capability=capability,
                        granted_by_user_id=membership.user_id,
                        granted_at=datetime.now(UTC),
                    )
                )
            await session.commit()

    asyncio.run(_insert())


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


@pytest.mark.parametrize("role", [WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
def test_owner_and_admin_can_create_and_toggle_definition(
    client_db: TestClient, role: WorkspaceRole
) -> None:
    user, headers = _auth(client_db, f"definition-{role.value}@example.com")
    _set_role(user["id"], role)
    created = client_db.post(URL, headers=headers, json=_payload(role.value))
    assert created.status_code == 201
    definition_id = created.json()["data"]["id"]
    disabled = client_db.patch(
        f"{URL}/{definition_id}", headers=headers, json={"is_active": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["is_active"] is False
    enabled = client_db.patch(
        f"{URL}/{definition_id}", headers=headers, json={"is_active": True}
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["is_active"] is True


def test_member_can_read_but_cannot_manage_definitions(client_db: TestClient) -> None:
    user, headers = _auth(client_db, "definition-member@example.com")
    created = client_db.post(URL, headers=headers, json=_payload("member_visible"))
    definition_id = created.json()["data"]["id"]
    _set_role(user["id"], WorkspaceRole.MEMBER)

    # Reading needs action.read; membership (dashboard.view) alone is denied.
    hidden = client_db.get(URL, headers=headers)
    assert hidden.status_code == 403
    assert "action.read" in hidden.json()["message"]
    assert "member_visible" not in hidden.text
    # action.operate never extends to definition changes (OWNER/ADMIN-only).
    _grant(user["id"], "action.read", "action.operate")
    assert client_db.get(URL, headers=headers).status_code == 200
    assert client_db.get(f"{URL}/{definition_id}", headers=headers).status_code == 200
    create_denied = client_db.post(URL, headers=headers, json=_payload("denied"))
    assert create_denied.status_code == 403
    assert create_denied.json()["error"]["code"] == "FORBIDDEN"
    patch_denied = client_db.patch(
        f"{URL}/{definition_id}", headers=headers, json={"is_active": False}
    )
    assert patch_denied.status_code == 403
    assert patch_denied.json()["error"]["code"] == "FORBIDDEN"


def test_definition_key_remains_immutable(client_db: TestClient) -> None:
    _, headers = _auth(client_db, "definition-immutable@example.com")
    created = client_db.post(URL, headers=headers, json=_payload("immutable"))
    definition_id = created.json()["data"]["id"]
    response = client_db.patch(
        f"{URL}/{definition_id}", headers=headers, json={"key": "changed"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["key"] == "immutable"


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
    assert (
        client_db.patch(
            f"{URL}/{definition_id}", headers=second, json={"is_active": False}
        ).status_code
        == 404
    )


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
