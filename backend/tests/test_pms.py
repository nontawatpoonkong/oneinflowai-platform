"""PostgreSQL-backed PMS adapter safety, isolation, and sync regressions."""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

import app.integrations.pms.registry as registry_module
from app.ai_tools.registry import create_ai_tool_registry
from app.integrations.pms.base import PMSProvider
from app.integrations.pms.contracts import (
    ImportedInventoryDay,
    ImportedProperty,
    ImportedRatePlan,
    PMSImportPage,
    PMSProviderCapabilities,
)
from app.integrations.pms.fake import FakePMSProvider
from app.integrations.pms.registry import PMSProviderRegistry
from app.integrations.pms.security import (
    EncryptedPMSCredentials,
    PMSCredentialCipher,
    PMSCredentialSecurityError,
)
from app.models.audit import WorkspaceAuditEvent
from app.models.hotel import InventoryDate, RatePlan
from app.models.pms import (
    PMSConnection,
    PMSExternalMapping,
    PMSReconciliationIssue,
    PMSSyncRun,
)
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_hotel import _inventory, _property, _rate, _room


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pms_registry(monkeypatch):
    registry = PMSProviderRegistry()
    monkeypatch.setattr(registry_module, "_registry", registry)
    return registry


def _account(client, prefix):
    client.headers["host"] = "localhost"
    return register_verify_and_login(
        client, email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    )


def _register(registry, provider):
    registry.register("fake", lambda _credentials: provider)


def _connection(client, token, *, authority="LOCAL", credentials=None):
    response = client.post(
        "/api/v1/pms/connections",
        headers=_auth(token),
        json={
            "provider": "fake",
            "name": "Hotel PMS",
            "credentials": credentials or {"api_key": "secret-never-return"},
            "sync_mode": "READ_ONLY_IMPORT",
            "inventory_authority": authority,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _catalog(client, token, *, reserved=1, blocked=1, total=5):
    prop = _property(client, token)
    room_type = _room(client, token, prop["id"])
    rate = _rate(client, token, prop["id"], room_type["id"])
    room = client.post(
        "/api/v1/hotel/rooms",
        headers=_auth(token),
        json={
            "property_id": prop["id"],
            "room_type_id": room_type["id"],
            "code": "101",
            "floor": "1",
        },
    )
    assert room.status_code == 201, room.text
    inventory = _inventory(
        client,
        token,
        prop["id"],
        room_type["id"],
        start_date="2030-01-01",
        end_date="2030-01-01",
        total_units=total,
        reserved_units=reserved,
        blocked_units=blocked,
    )
    assert inventory.status_code == 200, inventory.text
    return prop, room_type, rate, room.json()["data"]


def _map(client, token, connection_id, entity_type, external_id, local_id):
    response = client.post(
        "/api/v1/pms/mappings",
        headers=_auth(token),
        json={
            "connection_id": connection_id,
            "entity_type": entity_type,
            "external_id": external_id,
            "local_entity_id": local_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _inventory_provider(total_units):
    return FakePMSProvider(
        capabilities=PMSProviderCapabilities(inventory=True, incremental_sync=True),
        pages={
            "inventory": [
                PMSImportPage(
                    items=(
                        ImportedInventoryDay(
                            property_external_id="ext-property",
                            room_type_external_id="ext-room-type",
                            inventory_date=date(2030, 1, 1),
                            total_units=total_units,
                        ),
                    ),
                    next_cursor="1",
                ),
                PMSImportPage(items=()),
            ]
        },
    )


def test_provider_registry_and_read_only_contract():
    registry = PMSProviderRegistry()
    provider = FakePMSProvider()
    registry.register("fake", lambda _credentials: provider)
    assert registry.names() == ("fake",)
    assert registry.create("fake", {}) is provider
    with pytest.raises(ValueError, match="Unknown"):
        registry.create("missing", {})
    forbidden = {
        "create_booking",
        "update_booking",
        "update_inventory",
        "update_room",
        "check_in",
        "check_out",
    }
    assert forbidden.isdisjoint(dir(PMSProvider))


def test_normalized_payload_is_strict_and_cannot_choose_workspace():
    with pytest.raises(ValidationError):
        ImportedProperty.model_validate(
            {
                "external_id": "p1",
                "name": "Hotel",
                "workspace_id": str(uuid.uuid4()),
            }
        )


def test_credentials_encrypt_roundtrip_random_nonce_and_fail_closed():
    workspace_id, connection_id = uuid.uuid4(), uuid.uuid4()
    value = {"api_key": "not-real"}
    cipher = PMSCredentialCipher()
    first = cipher.encrypt(
        value,
        workspace_id=workspace_id,
        connection_id=connection_id,
        provider="fake",
    )
    second = cipher.encrypt(
        value,
        workspace_id=workspace_id,
        connection_id=connection_id,
        provider="fake",
    )
    assert first.ciphertext != second.ciphertext
    assert (
        cipher.decrypt(
            first,
            workspace_id=workspace_id,
            connection_id=connection_id,
            provider="fake",
        )
        == value
    )
    tampered = EncryptedPMSCredentials(
        first.ciphertext[:-1] + bytes([first.ciphertext[-1] ^ 1]),
        first.nonce,
        first.key_version,
    )
    with pytest.raises(PMSCredentialSecurityError):
        cipher.decrypt(
            tampered,
            workspace_id=workspace_id,
            connection_id=connection_id,
            provider="fake",
        )
    with pytest.raises(PMSCredentialSecurityError):
        cipher.decrypt(
            first,
            workspace_id=uuid.uuid4(),
            connection_id=connection_id,
            provider="fake",
        )


def test_connection_is_workspace_scoped_secret_safe_and_member_read_only(
    client_db, pms_registry, caplog
):
    provider = FakePMSProvider()
    _register(pms_registry, provider)
    account, token = _account(client_db, "pms-owner")
    secret = "pms-secret-never-return-or-log"
    with caplog.at_level(logging.DEBUG):
        connection = _connection(client_db, token, credentials={"api_key": secret})
    assert secret not in str(connection)
    assert secret not in caplog.text
    assert "credentials" not in connection

    async def inspect_and_demote():
        async with TestSessionLocal() as session:
            stored = await session.get(PMSConnection, uuid.UUID(connection["id"]))
            assert stored is not None
            assert secret.encode() not in stored.credential_ciphertext
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id
                    == uuid.UUID(account["workspace"]["id"]),
                    WorkspaceMember.user_id == uuid.UUID(account["user"]["id"]),
                )
            )
            membership.role = WorkspaceRole.MEMBER
            session.add(
                WorkspaceMemberCapability(
                    workspace_id=membership.workspace_id,
                    membership_id=membership.id,
                    capability="pms.read",
                    granted_by_user_id=membership.user_id,
                    granted_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(inspect_and_demote())
    assert (
        client_db.get("/api/v1/pms/connections", headers=_auth(token)).status_code
        == 200
    )
    assert (
        client_db.post(
            "/api/v1/pms/connections",
            headers=_auth(token),
            json={
                "provider": "fake",
                "name": "Denied",
                "credentials": {},
            },
        ).status_code
        == 403
    )

    _, other_token = _account(client_db, "pms-other")
    assert (
        client_db.get(
            f"/api/v1/pms/connections/{connection['id']}",
            headers=_auth(other_token),
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("auth", "PMS_AUTH_FAILED"),
        ("rate_limit", "PMS_RATE_LIMITED"),
        ("timeout", "PMS_TIMEOUT"),
        ("invalid", "PMS_INVALID_RESPONSE"),
    ],
)
def test_connection_test_maps_provider_errors(
    client_db, pms_registry, failure, expected
):
    provider = FakePMSProvider(failure=failure)
    _register(pms_registry, provider)
    _, token = _account(client_db, f"pms-{failure}")
    connection = _connection(client_db, token)
    response = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/test",
        headers=_auth(token),
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == expected
    assert "secret" not in response.text


def test_connection_test_success_updates_truthful_status(client_db, pms_registry):
    _register(pms_registry, FakePMSProvider())
    _, token = _account(client_db, "pms-test")
    connection = _connection(client_db, token)
    response = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/test",
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CONNECTED"
    assert response.json()["data"]["external_account_id"] == "fake-account"


@pytest.mark.parametrize(
    "entity_type,key",
    [
        ("PROPERTY", 0),
        ("ROOM_TYPE", 1),
        ("RATE_PLAN", 2),
        ("ROOM", 3),
    ],
)
def test_explicit_mapping_for_each_supported_entity(
    client_db, pms_registry, entity_type, key
):
    _register(pms_registry, FakePMSProvider())
    _, token = _account(client_db, f"pms-map-{entity_type.lower()}")
    connection = _connection(client_db, token)
    catalog = _catalog(client_db, token)
    mapping = _map(
        client_db,
        token,
        connection["id"],
        entity_type,
        f"external-{entity_type.lower()}",
        catalog[key]["id"],
    )
    assert mapping["entity_type"] == entity_type
    assert mapping["local_entity_id"] == catalog[key]["id"]


def test_mapping_uniqueness_and_cross_workspace_target_rejected(
    client_db, pms_registry
):
    _register(pms_registry, FakePMSProvider())
    _, token = _account(client_db, "pms-map-a")
    connection = _connection(client_db, token)
    prop = _property(client_db, token)
    _map(client_db, token, connection["id"], "PROPERTY", "external", prop["id"])
    duplicate = client_db.post(
        "/api/v1/pms/mappings",
        headers=_auth(token),
        json={
            "connection_id": connection["id"],
            "entity_type": "PROPERTY",
            "external_id": "external",
            "local_entity_id": prop["id"],
        },
    )
    assert duplicate.status_code == 409

    _, other_token = _account(client_db, "pms-map-b")
    other_prop = _property(client_db, other_token)
    wrong_workspace = client_db.post(
        "/api/v1/pms/mappings",
        headers=_auth(token),
        json={
            "connection_id": connection["id"],
            "entity_type": "PROPERTY",
            "external_id": "other",
            "local_entity_id": other_prop["id"],
        },
    )
    assert wrong_workspace.status_code == 422


def test_pms_authoritative_inventory_import_is_idempotent_and_cursor_durable(
    client_db, pms_registry
):
    provider = _inventory_provider(8)
    _register(pms_registry, provider)
    _, token = _account(client_db, "pms-inventory")
    connection = _connection(client_db, token, authority="PMS")
    prop, room_type, _, _ = _catalog(client_db, token)
    _map(client_db, token, connection["id"], "PROPERTY", "ext-property", prop["id"])
    _map(
        client_db,
        token,
        connection["id"],
        "ROOM_TYPE",
        "ext-room-type",
        room_type["id"],
    )
    first = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/sync",
        headers=_auth(token),
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["status"] == "SUCCEEDED"
    assert first.json()["data"]["entities_applied"] == 1
    second = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/sync",
        headers=_auth(token),
    )
    assert second.status_code == 200
    assert second.json()["data"]["entities_applied"] == 0

    async def verify():
        async with TestSessionLocal() as session:
            inventory = await session.scalar(
                select(InventoryDate).where(
                    InventoryDate.room_type_id == uuid.UUID(room_type["id"]),
                    InventoryDate.inventory_date == date(2030, 1, 1),
                )
            )
            assert inventory.total_units == 8
            stored = await session.get(PMSConnection, uuid.UUID(connection["id"]))
            assert stored.sync_cursor == {"inventory": "1"}
            assert (await session.scalar(select(func.count(PMSSyncRun.id)))) == 2
            audit_actions = set(
                await session.scalars(select(WorkspaceAuditEvent.action))
            )
            assert {
                "PMS_CONNECTION_CREATED",
                "PMS_MAPPING_CHANGED",
                "PMS_SYNC_STARTED",
                "PMS_SYNC_COMPLETED",
            } <= audit_actions

    asyncio.run(verify())


def test_external_inventory_below_local_commitment_is_never_applied(
    client_db, pms_registry
):
    _register(pms_registry, _inventory_provider(2))
    _, token = _account(client_db, "pms-conflict")
    connection = _connection(client_db, token, authority="PMS")
    prop, room_type, _, _ = _catalog(client_db, token, reserved=2, blocked=1, total=5)
    _map(client_db, token, connection["id"], "PROPERTY", "ext-property", prop["id"])
    _map(
        client_db,
        token,
        connection["id"],
        "ROOM_TYPE",
        "ext-room-type",
        room_type["id"],
    )
    result = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/sync",
        headers=_auth(token),
    )
    assert result.status_code == 200
    assert result.json()["data"]["status"] == "PARTIAL"
    assert result.json()["data"]["conflict_count"] == 1

    async def verify():
        async with TestSessionLocal() as session:
            inventory = await session.scalar(
                select(InventoryDate).where(
                    InventoryDate.room_type_id == uuid.UUID(room_type["id"])
                )
            )
            assert inventory.total_units == 5
            issue = await session.scalar(select(PMSReconciliationIssue))
            assert issue.issue_type == "INVENTORY_BELOW_LOCAL_RESERVED"
            stored = await session.get(PMSConnection, uuid.UUID(connection["id"]))
            assert stored.sync_cursor == {}

    asyncio.run(verify())


def test_local_authority_reconciles_without_overwrite(client_db, pms_registry):
    _register(pms_registry, _inventory_provider(8))
    _, token = _account(client_db, "pms-local")
    connection = _connection(client_db, token, authority="LOCAL")
    prop, room_type, _, _ = _catalog(client_db, token)
    _map(client_db, token, connection["id"], "PROPERTY", "ext-property", prop["id"])
    _map(
        client_db,
        token,
        connection["id"],
        "ROOM_TYPE",
        "ext-room-type",
        room_type["id"],
    )
    result = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/sync",
        headers=_auth(token),
    )
    assert result.json()["data"]["status"] == "PARTIAL"
    issues = client_db.get(
        "/api/v1/pms/reconciliation/issues",
        headers=_auth(token),
    ).json()["data"]
    assert issues[0]["issue_type"] == "INVENTORY_DIFFERENCE"

    async def verify():
        async with TestSessionLocal() as session:
            inventory = await session.scalar(
                select(InventoryDate).where(
                    InventoryDate.room_type_id == uuid.UUID(room_type["id"])
                )
            )
            assert inventory.total_units == 5

    asyncio.run(verify())


def test_unmapped_entity_and_rate_difference_are_reconciliation_only(
    client_db, pms_registry
):
    provider = FakePMSProvider(
        capabilities=PMSProviderCapabilities(properties=True, rate_plans=True),
        pages={
            "properties": [
                PMSImportPage(
                    items=(ImportedProperty(external_id="unmapped", name="PMS Hotel"),)
                )
            ],
            "rate_plans": [
                PMSImportPage(
                    items=(
                        ImportedRatePlan(
                            external_id="ext-rate",
                            property_external_id="ext-property",
                            room_type_external_id="ext-room-type",
                            name="External Rate",
                            currency="THB",
                            base_price=Decimal("999.00"),
                        ),
                    )
                )
            ],
        },
    )
    _register(pms_registry, provider)
    _, token = _account(client_db, "pms-reconcile")
    connection = _connection(client_db, token)
    _, _, rate, _ = _catalog(client_db, token)
    _map(
        client_db,
        token,
        connection["id"],
        "RATE_PLAN",
        "ext-rate",
        rate["id"],
    )
    result = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/sync",
        headers=_auth(token),
    )
    assert result.json()["data"]["status"] == "PARTIAL"
    issues = client_db.get(
        "/api/v1/pms/reconciliation/issues",
        headers=_auth(token),
    ).json()["data"]
    assert {item["issue_type"] for item in issues} == {
        "UNMAPPED_PROPERTY",
        "RATE_DIFFERENCE",
    }

    async def verify():
        async with TestSessionLocal() as session:
            stored = await session.get(RatePlan, uuid.UUID(rate["id"]))
            assert stored.base_price == Decimal("1500.25")

    asyncio.run(verify())


def test_duplicate_sync_request_returns_conflict(client_db, pms_registry):
    _register(pms_registry, FakePMSProvider())
    account, token = _account(client_db, "pms-concurrent")
    connection = _connection(client_db, token)

    async def running():
        async with TestSessionLocal() as session:
            session.add(
                PMSSyncRun(
                    workspace_id=uuid.UUID(account["workspace"]["id"]),
                    connection_id=uuid.UUID(connection["id"]),
                    status="RUNNING",
                    cursor_before={},
                )
            )
            await session.commit()

    asyncio.run(running())
    result = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/sync",
        headers=_auth(token),
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "PMS_SYNC_CONFLICT"


def test_sync_retry_is_service_owned_bounded_and_failure_does_not_advance_cursor(
    client_db, pms_registry
):
    provider = FakePMSProvider(
        failure="rate_limit",
        capabilities=PMSProviderCapabilities(inventory=True),
    )
    _register(pms_registry, provider)
    _, token = _account(client_db, "pms-retry")
    connection = _connection(client_db, token, authority="PMS")
    result = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/sync",
        headers=_auth(token),
    )
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "PMS_RATE_LIMITED"
    assert provider.calls["inventory"] == 3

    async def verify():
        async with TestSessionLocal() as session:
            run = await session.scalar(select(PMSSyncRun))
            stored = await session.get(PMSConnection, uuid.UUID(connection["id"]))
            assert run.status == "FAILED"
            assert run.error_code == "PMS_RATE_LIMITED"
            assert stored.sync_cursor == {}

    asyncio.run(verify())


def test_invalid_encrypted_credentials_fail_sync_without_stuck_run(
    client_db, pms_registry
):
    _register(pms_registry, FakePMSProvider())
    _, token = _account(client_db, "pms-invalid-credentials")
    connection = _connection(client_db, token)

    async def tamper():
        async with TestSessionLocal() as session:
            stored = await session.get(PMSConnection, uuid.UUID(connection["id"]))
            stored.credential_ciphertext = b"tampered"
            await session.commit()

    asyncio.run(tamper())
    result = client_db.post(
        f"/api/v1/pms/connections/{connection['id']}/sync",
        headers=_auth(token),
    )
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "PMS_UNAVAILABLE"

    async def verify():
        async with TestSessionLocal() as session:
            run = await session.scalar(select(PMSSyncRun))
            stored = await session.get(PMSConnection, uuid.UUID(connection["id"]))
            assert run.status == "FAILED"
            assert run.error_code == "PMS_SYNC_FAILED"
            assert run.completed_at is not None
            assert stored.sync_cursor == {}

    asyncio.run(verify())


def test_mapping_and_issue_rows_are_not_duplicated_by_retry(client_db, pms_registry):
    _register(pms_registry, _inventory_provider(8))
    _, token = _account(client_db, "pms-idempotency")
    connection = _connection(client_db, token, authority="LOCAL")
    prop, room_type, _, _ = _catalog(client_db, token)
    _map(client_db, token, connection["id"], "PROPERTY", "ext-property", prop["id"])
    _map(
        client_db,
        token,
        connection["id"],
        "ROOM_TYPE",
        "ext-room-type",
        room_type["id"],
    )
    for _ in range(2):
        response = client_db.post(
            f"/api/v1/pms/connections/{connection['id']}/sync",
            headers=_auth(token),
        )
        assert response.status_code == 200

    async def verify():
        async with TestSessionLocal() as session:
            assert await session.scalar(select(func.count(PMSExternalMapping.id))) == 2
            assert (
                await session.scalar(select(func.count(PMSReconciliationIssue.id))) == 1
            )

    asyncio.run(verify())


def test_ai_registry_has_no_pms_administration_tools():
    assert all("pms" not in item.name for item in create_ai_tool_registry().list())
