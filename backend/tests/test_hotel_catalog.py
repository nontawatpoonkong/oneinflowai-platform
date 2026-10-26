"""Sprint 10.9C rich room catalog and availability calendar regressions."""

import asyncio
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.core.exceptions import NotFoundError
from app.models.audit import WorkspaceAuditEvent
from app.models.hotel import InventoryDate
from app.models.hotel_catalog import RoomTypeImage
from app.models.pms import (
    PMSConnection,
    PMSConnectionStatus,
    PMSEntityType,
    PMSExternalMapping,
    PMSInventoryAuthority,
    PMSSyncMode,
)
from app.models.stay import HotelRoom
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.hotel_catalog import RoomTypeImageCreate, RoomTypeImageOrderItem
from app.services.hotel_catalog import (
    AvailabilityCalendarService,
    RichHotelCatalogService,
)
from app.storage.base import StorageProvider
from tests.conftest import TestSessionLocal, register_verify_and_login


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _owner(client, email: str = "catalog-owner@example.com"):
    client.headers["host"] = "localhost"
    data, token = register_verify_and_login(client, email=email)
    return data["workspace"]["id"], token


def _property(client, token, name="ABC Hotel"):
    response = client.post(
        "/api/v1/hotel/properties",
        headers=_auth(token),
        json={"name": name, "timezone": "Asia/Bangkok", "currency": "THB"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _rich_payload(property_id: str, code: str = "DELUXE"):
    return {
        "property_id": property_id,
        "code": code,
        "name": "Deluxe King Mountain View",
        "short_description": "Mountain-facing king room",
        "description": "A spacious room with a private bathroom.",
        "room_size_sqm": "42.50",
        "max_adults": 2,
        "max_children": 1,
        "max_occupancy": 3,
        "base_capacity": 2,
        "smoking_policy": "NON_SMOKING",
        "accessibility_available": True,
        "public_highlights": "Quiet upper-floor room",
        "view_type": "MOUNTAIN",
        "beds": [
            {"bed_type": "KING", "quantity": 1, "sort_order": 0},
            {"bed_type": "SOFA_BED", "quantity": 1, "sort_order": 1},
        ],
        "amenities": [
            {"code": "water_heater", "boolean_value": True},
            {"code": "hair_dryer", "boolean_value": True},
            {"code": "refrigerator", "boolean_value": True},
            {"code": "tv_size_inches", "number_value": "55"},
            {"code": "custom_amenity", "text_value": "Yoga mat"},
        ],
        "physical_rooms": [
            {"code": "301", "floor": "3", "building": "A", "wing": "East"},
            {"code": "302", "floor": "3", "building": "A", "wing": "East"},
        ],
    }


def _create_rich(client, token, property_id, **changes):
    payload = {**_rich_payload(property_id), **changes}
    response = client.post(
        "/api/v1/hotel/catalog/room-types", headers=_auth(token), json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_create_rich_room_type_beds_amenities_and_physical_count(client_db):
    workspace_id, token = _owner(client_db)
    prop = _property(client_db, token)
    detail = _create_rich(client_db, token, prop["id"])

    room = detail["room_type"]
    assert room["room_size_sqm"] == "42.50"
    assert room["view_type"] == "MOUNTAIN"
    assert room["accessibility_available"] is True
    assert [bed["bed_type"] for bed in detail["beds"]] == ["KING", "SOFA_BED"]
    assert detail["physical_room_count"] == 2
    amenities = {item["code"]: item for item in detail["amenities"]}
    assert amenities["water_heater"]["boolean_value"] is True
    assert amenities["hair_dryer"]["boolean_value"] is True
    assert amenities["refrigerator"]["boolean_value"] is True
    assert amenities["tv_size_inches"]["number_value"] == "55.00"
    registry = client_db.get("/api/v1/hotel/catalog/amenities", headers=_auth(token))
    assert registry.status_code == 200
    definitions = {item["code"]: item for item in registry.json()["data"]}
    assert definitions["hair_dryer"]["value_type"] == "BOOLEAN"
    assert definitions["tv_size_inches"]["value_type"] == "NUMBER"
    assert definitions["custom_amenity"]["value_type"] == "TEXT"
    one_bed = client_db.put(
        f"/api/v1/hotel/catalog/room-types/{room['id']}/beds",
        headers=_auth(token),
        json=[{"bed_type": "QUEEN", "quantity": 1, "sort_order": 0}],
    )
    assert one_bed.status_code == 200
    bed_values = [
        (item["bed_type"], item["quantity"]) for item in one_bed.json()["data"]
    ]
    assert bed_values == [("QUEEN", 1)]

    async def audit_actions():
        async with TestSessionLocal() as session:
            return set(
                await session.scalars(
                    select(WorkspaceAuditEvent.action).where(
                        WorkspaceAuditEvent.workspace_id == uuid.UUID(workspace_id)
                    )
                )
            )

    assert {
        "PROPERTY_CREATED",
        "ROOM_TYPE_CREATED",
    } <= asyncio.run(audit_actions())


def test_update_metadata_and_custom_view_validation(client_db):
    _, token = _owner(client_db, "catalog-update@example.com")
    prop = _property(client_db, token)
    detail = _create_rich(client_db, token, prop["id"])
    room_id = detail["room_type"]["id"]
    changed = client_db.patch(
        f"/api/v1/hotel/room-types/{room_id}",
        headers=_auth(token),
        json={"short_description": "Updated", "view_type": "CITY"},
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["short_description"] == "Updated"
    invalid = client_db.post(
        "/api/v1/hotel/catalog/room-types",
        headers=_auth(token),
        json={**_rich_payload(prop["id"], "CUSTOM"), "view_type": "CUSTOM"},
    )
    assert invalid.status_code == 422

    custom = _create_rich(
        client_db,
        token,
        prop["id"],
        code="CUSTOM-VALID",
        view_type="CUSTOM",
        custom_view_label="Old town skyline",
        physical_rooms=[{"code": "401", "floor": "4", "building": "A", "wing": "East"}],
    )
    standard = client_db.patch(
        f"/api/v1/hotel/room-types/{custom['room_type']['id']}",
        headers=_auth(token),
        json={"view_type": "CITY"},
    )
    assert standard.status_code == 200, standard.text
    assert standard.json()["data"]["custom_view_label"] is None


@pytest.mark.parametrize(
    ("amenity", "expected"),
    [
        ({"code": "television", "boolean_value": True}, 200),
        ({"code": "tv_size_inches", "number_value": "65"}, 200),
        ({"code": "tv_size_inches", "boolean_value": True}, 422),
        ({"code": "custom_amenity", "text_value": "<script>x</script>"}, 422),
    ],
)
def test_amenity_value_types_and_custom_text_are_enforced(client_db, amenity, expected):
    workspace_id, token = _owner(client_db, f"amenity-{uuid.uuid4()}@example.com")
    prop = _property(client_db, token)
    detail = _create_rich(client_db, token, prop["id"], amenities=[])
    response = client_db.put(
        f"/api/v1/hotel/catalog/room-types/{detail['room_type']['id']}/amenities",
        headers=_auth(token),
        json=[amenity],
    )
    assert response.status_code == expected, response.text
    if expected == 200:

        async def audit_count():
            async with TestSessionLocal() as session:
                return await session.scalar(
                    select(func.count())
                    .select_from(WorkspaceAuditEvent)
                    .where(
                        WorkspaceAuditEvent.workspace_id
                        == uuid.UUID(workspace_id),
                        WorkspaceAuditEvent.action == "ROOM_AMENITIES_CHANGED",
                        WorkspaceAuditEvent.resource_id
                        == uuid.UUID(detail["room_type"]["id"]),
                    )
                )

        assert asyncio.run(audit_count()) == 1


def test_duplicate_amenity_and_invalid_bed_quantity_are_rejected(client_db):
    _, token = _owner(client_db, "catalog-invalid@example.com")
    prop = _property(client_db, token)
    room = _create_rich(client_db, token, prop["id"], beds=[], amenities=[])
    room_id = room["room_type"]["id"]
    duplicate = client_db.put(
        f"/api/v1/hotel/catalog/room-types/{room_id}/amenities",
        headers=_auth(token),
        json=[
            {"code": "wifi", "boolean_value": True},
            {"code": "wifi", "boolean_value": False},
        ],
    )
    assert duplicate.status_code == 422
    invalid_bed = client_db.put(
        f"/api/v1/hotel/catalog/room-types/{room_id}/beds",
        headers=_auth(token),
        json=[{"bed_type": "KING", "quantity": 0}],
    )
    assert invalid_bed.status_code == 422
    duplicate_room_codes = client_db.post(
        "/api/v1/hotel/catalog/room-types",
        headers=_auth(token),
        json=_rich_payload(prop["id"], "DUPLICATE-CODES"),
    )
    assert duplicate_room_codes.status_code == 409


class _MemoryStorage(StorageProvider):
    def __init__(self):
        self.values: dict[str, bytes] = {}

    async def save(self, *, key: str, data: bytes) -> None:
        self.values[key] = data

    async def read(self, *, key: str) -> bytes:
        return self.values[key]

    async def delete(self, *, key: str) -> None:
        self.values.pop(key, None)


def test_image_metadata_cover_order_and_no_binary_column(client_db):
    workspace_id, token = _owner(client_db, "catalog-image@example.com")
    prop = _property(client_db, token)
    detail = _create_rich(client_db, token, prop["id"], beds=[], amenities=[])
    room_type_id = detail["room_type"]["id"]
    storage = _MemoryStorage()

    async def run():
        async with TestSessionLocal() as session:
            service = RichHotelCatalogService(session, storage=storage)
            first = await service.add_image(
                uuid.UUID(workspace_id),
                uuid.UUID(room_type_id),
                RoomTypeImageCreate(
                    alt_text="Deluxe room", is_cover=True, sort_order=0
                ),
                b"\x89PNG\r\n\x1a\nimage",
                "image/png",
            )
            second = await service.add_image(
                uuid.UUID(workspace_id),
                uuid.UUID(room_type_id),
                RoomTypeImageCreate(
                    alt_text="Mountain view", is_cover=True, sort_order=1
                ),
                b"\x89PNG\r\n\x1a\nimage2",
                "image/png",
            )
            values = list(
                (
                    await session.scalars(
                        select(RoomTypeImage)
                        .where(RoomTypeImage.room_type_id == uuid.UUID(room_type_id))
                        .order_by(RoomTypeImage.sort_order)
                    )
                ).all()
            )
            assert first.is_cover is True and second.is_cover is True
            assert [item.is_cover for item in values] == [False, True]
            assert [item.sort_order for item in values] == [0, 1]
            assert "data" not in RoomTypeImage.__table__.columns
            assert "binary" not in RoomTypeImage.__table__.columns
            ordered = await service.reorder_images(
                uuid.UUID(workspace_id),
                uuid.UUID(room_type_id),
                [
                    RoomTypeImageOrderItem(
                        image_id=second.id, sort_order=0, is_cover=False
                    ),
                    RoomTypeImageOrderItem(
                        image_id=first.id, sort_order=1, is_cover=True
                    ),
                ],
            )
            assert [item.id for item in ordered] == [first.id, second.id]
            assert [item.sort_order for item in ordered] == [1, 0]
            assert [item.is_cover for item in ordered] == [True, False]
            with pytest.raises(NotFoundError):
                await service.image_content(
                    uuid.uuid4(), uuid.UUID(room_type_id), first.id
                )

    asyncio.run(run())


def test_workspace_isolation_and_customer_facts_exclude_internal_notes(client_db):
    first_id, first = _owner(client_db, "catalog-first@example.com")
    prop = _property(client_db, first)
    detail = _create_rich(client_db, first, prop["id"])
    room_type_id = detail["room_type"]["id"]
    _, second = _owner(client_db, "catalog-second@example.com")
    assert (
        client_db.get(
            f"/api/v1/hotel/catalog/room-types/{room_type_id}", headers=_auth(second)
        ).status_code
        == 404
    )
    facts = client_db.get(
        f"/api/v1/hotel/catalog/room-types/{room_type_id}/customer-facts",
        headers=_auth(first),
    )
    assert facts.status_code == 200
    body = facts.json()["data"]
    assert "internal_notes" not in body
    assert body["physical_room_count"] == 2
    assert first_id != body["room_type_id"]
    isolated_calendar = client_db.get(
        "/api/v1/hotel/availability-calendar",
        headers=_auth(second),
        params={"property_id": prop["id"], "start_date": "2030-10-05", "days": 7},
    )
    assert isolated_calendar.status_code == 404


@pytest.mark.parametrize("days", [7, 14, 30])
def test_availability_calendar_ranges_and_counts(client_db, days):
    _, token = _owner(client_db, f"calendar-{days}@example.com")
    prop = _property(client_db, token)
    detail = _create_rich(client_db, token, prop["id"], beds=[], amenities=[])
    room_type_id = detail["room_type"]["id"]
    inventory = client_db.put(
        "/api/v1/hotel/inventory",
        headers=_auth(token),
        json={
            "property_id": prop["id"],
            "room_type_id": room_type_id,
            "start_date": "2030-10-05",
            "end_date": "2030-10-05",
            "total_units": 10,
            "reserved_units": 5,
            "blocked_units": 1,
        },
    )
    assert inventory.status_code == 200
    response = client_db.get(
        "/api/v1/hotel/availability-calendar",
        headers=_auth(token),
        params={"property_id": prop["id"], "start_date": "2030-10-05", "days": days},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["rows"][0]["cells"]) == days
    cell = data["rows"][0]["cells"][0]
    assert cell == {
        "date": "2030-10-05",
        "total_units": 10,
        "reserved_units": 5,
        "blocked_units": 1,
        "available_units": 4,
        "used_units": 6,
        "occupancy_ratio": "60.00",
        "color_bucket": "YELLOW",
        "authority": "LOCAL",
        "has_inventory": True,
    }
    assert data["rows"][0]["cells"][1]["has_inventory"] is False


def test_invalid_calendar_range_and_color_boundaries(client_db):
    _, token = _owner(client_db, "calendar-invalid@example.com")
    prop = _property(client_db, token)
    response = client_db.get(
        "/api/v1/hotel/availability-calendar",
        headers=_auth(token),
        params={"property_id": prop["id"], "start_date": "2030-10-05", "days": 365},
    )
    assert response.status_code == 422
    bucket = AvailabilityCalendarService.color_bucket
    assert [
        bucket(Decimal(value)) for value in ("39", "40", "69", "70", "89", "90")
    ] == ["GREEN", "YELLOW", "YELLOW", "ORANGE", "ORANGE", "RED"]


def test_pms_authority_is_derived_from_existing_connection_mapping(client_db):
    workspace_id, token = _owner(client_db, "calendar-pms@example.com")
    prop = _property(client_db, token)
    detail = _create_rich(client_db, token, prop["id"], beds=[], amenities=[])

    async def seed():
        async with TestSessionLocal() as session:
            connection = PMSConnection(
                workspace_id=uuid.UUID(workspace_id),
                provider="test",
                name="PMS",
                active=True,
                status=PMSConnectionStatus.CONNECTED.value,
                sync_mode=PMSSyncMode.READ_ONLY_IMPORT.value,
                inventory_authority=PMSInventoryAuthority.PMS.value,
                credential_ciphertext=b"cipher",
                credential_nonce=b"nonce",
                credential_key_version="v1",
            )
            session.add(connection)
            await session.flush()
            session.add(
                PMSExternalMapping(
                    workspace_id=uuid.UUID(workspace_id),
                    connection_id=connection.id,
                    entity_type=PMSEntityType.PROPERTY.value,
                    external_id="hotel-1",
                    local_entity_id=uuid.UUID(prop["id"]),
                )
            )
            session.add(
                InventoryDate(
                    workspace_id=uuid.UUID(workspace_id),
                    property_id=uuid.UUID(prop["id"]),
                    room_type_id=uuid.UUID(detail["room_type"]["id"]),
                    inventory_date=date(2030, 10, 5),
                    total_units=2,
                    reserved_units=1,
                    blocked_units=0,
                )
            )
            await session.commit()

    asyncio.run(seed())
    response = client_db.get(
        "/api/v1/hotel/availability-calendar",
        headers=_auth(token),
        params={"property_id": prop["id"], "start_date": "2030-10-05", "days": 7},
    )
    assert response.status_code == 200
    assert response.json()["data"]["rows"][0]["cells"][0]["authority"] == "PMS"


def test_room_read_and_manage_capabilities_are_enforced(client_db):
    workspace_id, token = _owner(client_db, "catalog-permission@example.com")
    prop = _property(client_db, token)

    async def demote_and_grant(capabilities):
        async with TestSessionLocal() as session:
            member = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == uuid.UUID(workspace_id)
                )
            )
            member.role = WorkspaceRole.MEMBER
            await session.execute(
                delete(WorkspaceMemberCapability).where(
                    WorkspaceMemberCapability.membership_id == member.id
                )
            )
            for capability in capabilities:
                session.add(
                    WorkspaceMemberCapability(
                        workspace_id=member.workspace_id,
                        membership_id=member.id,
                        capability=capability,
                        granted_by_user_id=member.user_id,
                        granted_at=datetime.now(UTC),
                    )
                )
            await session.commit()

    asyncio.run(demote_and_grant([]))
    assert (
        client_db.get(
            f"/api/v1/hotel/catalog/room-types/{uuid.uuid4()}", headers=_auth(token)
        ).status_code
        == 403
    )
    asyncio.run(demote_and_grant(["room.read"]))
    assert (
        client_db.get(
            "/api/v1/hotel/availability-calendar",
            headers=_auth(token),
            params={"property_id": prop["id"], "start_date": "2030-10-05", "days": 7},
        ).status_code
        == 200
    )
    denied = client_db.post(
        "/api/v1/hotel/catalog/room-types",
        headers=_auth(token),
        json=_rich_payload(prop["id"], "MEMBER"),
    )
    assert denied.status_code == 403


def test_physical_room_details_preserve_operational_readiness(client_db):
    _, token = _owner(client_db, "catalog-room-details@example.com")
    prop = _property(client_db, token)
    detail = _create_rich(client_db, token, prop["id"])
    response = client_db.get(
        "/api/v1/hotel/rooms",
        headers=_auth(token),
        params={"floor": "3", "building": "A", "wing": "East"},
    )
    assert response.status_code == 200
    rooms = response.json()["data"]["items"]
    assert len(rooms) == detail["physical_room_count"] == 2
    assert all(item["operational_status"] == "AVAILABLE" for item in rooms)
    assert all(item["readiness_status"] == "READY" for item in rooms)
    assert all(item["building"] == "A" and item["wing"] == "East" for item in rooms)


def test_active_physical_room_count_is_authoritative(client_db):
    workspace_id, token = _owner(client_db, "catalog-count@example.com")
    prop = _property(client_db, token)
    detail = _create_rich(client_db, token, prop["id"])
    room_type_id = detail["room_type"]["id"]

    async def deactivate_one():
        async with TestSessionLocal() as session:
            room = await session.scalar(
                select(HotelRoom)
                .where(
                    HotelRoom.workspace_id == uuid.UUID(workspace_id),
                    HotelRoom.room_type_id == uuid.UUID(room_type_id),
                )
                .limit(1)
            )
            room.active = False
            await session.commit()

    asyncio.run(deactivate_one())
    refreshed = client_db.get(
        f"/api/v1/hotel/catalog/room-types/{room_type_id}", headers=_auth(token)
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["physical_room_count"] == 1
