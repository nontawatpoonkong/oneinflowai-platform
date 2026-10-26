"""Platform campaign catalog-target reads: Workspace-scoped, paginated,
whitelisted, limited to DRAFT campaigns of ACTIVE Workspaces, and audited once
per admin and campaign access window."""

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import update

import app.services.platform_campaign as platform_campaign_module
from app.models.promotion import PromotionCampaign
from tests.conftest import TestSessionLocal
from tests.test_booking import _setup
from tests.test_campaign_operations import P, _audits, _platform_campaign
from tests.test_hotel import _auth, _property, _rate, _room
from tests.test_platform_admin import _confirmed, _platform_admin

CATALOG_KEYS = {
    "id",
    "kind",
    "name",
    "code",
    "active",
    "property_id",
    "room_type_id",
    "currency",
}


def _catalog(client, headers, campaign_id, **params):
    return client.get(
        f"{P}/campaigns/{campaign_id}/catalog", headers=headers, params=params
    )


def test_catalog_requires_platform_admin(client_db):
    user, token, *_ = _setup(client_db)
    _, admin = _platform_admin(client_db)
    detail = _platform_campaign(client_db, admin, user["workspace"]["id"])
    response = _catalog(
        client_db, _auth(token), detail["campaign"]["id"], kind="property"
    )
    # Workspace OWNER never inherits platform authority.
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"


def test_catalog_is_scoped_whitelisted_and_audited(client_db):
    user, _, prop, room, plan = _setup(client_db)
    other, _, other_prop, *_ = _setup(client_db, email="other-owner@example.com")
    _, admin = _platform_admin(client_db)
    detail = _platform_campaign(client_db, admin, user["workspace"]["id"])
    campaign_id = detail["campaign"]["id"]

    seen = {}
    for kind, expected in (
        ("property", prop),
        ("room_type", room),
        ("rate_plan", plan),
    ):
        response = _catalog(client_db, admin, campaign_id, kind=kind)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert [item["id"] for item in data["items"]] == [expected["id"]]
        assert set(data["items"][0]) == CATALOG_KEYS
        seen[kind] = data["items"][0]
    # The Workspace comes from the campaign, so another Workspace never leaks.
    assert other_prop["id"] not in {item["id"] for item in seen.values()}
    assert seen["rate_plan"] == {
        "id": plan["id"],
        "kind": "rate_plan",
        "name": plan["name"],
        "code": plan["code"],
        "active": True,
        "property_id": prop["id"],
        "room_type_id": room["id"],
        "currency": "THB",
    }
    body = _catalog(client_db, admin, campaign_id, kind="rate_plan").text.lower()
    for fragment in ("base_price", "description", "cancellation", "guest"):
        assert fragment not in body, fragment

    # Four reads inside one access window produce one audit event.
    events = _audits(
        uuid.UUID(user["workspace"]["id"]), action="PLATFORM_CATALOG_VIEWED"
    )
    assert len(events) == 1
    event = events[0]
    assert event.actor_type == "PLATFORM_ADMIN"
    assert event.resource_type == "HotelCatalog" and event.resource_id is None
    assert event.safe_metadata["campaign_id"] == campaign_id
    assert event.safe_metadata["kind"] == "property"
    assert event.safe_metadata["window_seconds"] == 900
    assert not _audits(
        uuid.UUID(other["workspace"]["id"]), action="PLATFORM_CATALOG_VIEWED"
    )
    # Catalog reads do not crowd the campaign's own audit trail.
    trail = client_db.get(f"{P}/campaigns/{campaign_id}", headers=admin).json()
    assert "PLATFORM_CATALOG_VIEWED" not in {
        item["action"] for item in trail["data"]["audit"]
    }


def test_catalog_filters_paginate_and_reject_invalid_queries(client_db):
    user, token, prop, room, plan = _setup(client_db)
    _, _, other_prop, *_ = _setup(client_db, email="other-owner@example.com")
    second = _property(client_db, token, name="Beach Annex")
    second_room = _room(client_db, token, second["id"], code="SUITE", name="Suite")
    second_plan = _rate(client_db, token, second["id"], second_room["id"])
    _, admin = _platform_admin(client_db)
    campaign_id = _platform_campaign(client_db, admin, user["workspace"]["id"])[
        "campaign"
    ]["id"]

    first = _catalog(client_db, admin, campaign_id, kind="property", page_size=1)
    data = first.json()["data"]
    assert data["total"] == 2 and data["total_pages"] == 2
    # Ordered by name: "ABC Hotel" before "Beach Annex".
    assert data["items"][0]["id"] == prop["id"]
    page_two = _catalog(
        client_db, admin, campaign_id, kind="property", page_size=1, page=2
    ).json()["data"]
    assert [item["id"] for item in page_two["items"]] == [second["id"]]

    rooms = _catalog(
        client_db, admin, campaign_id, kind="room_type", property_id=second["id"]
    ).json()["data"]
    assert [item["id"] for item in rooms["items"]] == [second_room["id"]]
    plans = _catalog(
        client_db, admin, campaign_id, kind="rate_plan", room_type_id=room["id"]
    ).json()["data"]
    assert [item["id"] for item in plans["items"]] == [plan["id"]]
    assert second_plan["id"] not in {item["id"] for item in plans["items"]}

    searched = _catalog(
        client_db, admin, campaign_id, kind="room_type", search="suit"
    ).json()["data"]
    assert [item["id"] for item in searched["items"]] == [second_room["id"]]
    wildcard = _catalog(
        client_db, admin, campaign_id, kind="property", search="%%"
    ).json()["data"]
    assert wildcard["total"] == 0

    deactivated = client_db.patch(
        f"/api/v1/hotel/properties/{second['id']}",
        headers=_auth(token),
        json={"active": False},
    )
    assert deactivated.status_code == 200, deactivated.text
    active = _catalog(client_db, admin, campaign_id, kind="property").json()["data"]
    assert [item["id"] for item in active["items"]] == [prop["id"]]
    every = _catalog(
        client_db, admin, campaign_id, kind="property", active_only="false"
    ).json()["data"]
    assert {item["id"]: item["active"] for item in every["items"]} == {
        prop["id"]: True,
        second["id"]: False,
    }

    foreign = _catalog(
        client_db, admin, campaign_id, kind="room_type", property_id=other_prop["id"]
    )
    assert foreign.status_code == 404
    for params in (
        {"kind": "property", "property_id": prop["id"]},
        {"kind": "room_type", "room_type_id": room["id"]},
    ):
        response = _catalog(client_db, admin, campaign_id, **params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "PLATFORM_CATALOG_FILTER_INVALID"
    for params in (
        {"kind": "property", "page_size": 101},
        {"kind": "property", "page": 0},
        {"kind": "property", "search": "x"},
        {"kind": "guest"},
        {},
    ):
        assert _catalog(client_db, admin, campaign_id, **params).status_code == 422
    missing = _catalog(client_db, admin, uuid.uuid4(), kind="property")
    assert missing.status_code == 404


def test_active_only_hides_targets_under_inactive_parents(client_db):
    user, token, prop, room, plan = _setup(client_db)
    legacy = _room(client_db, token, prop["id"], code="LEGACY", name="Legacy Room")
    legacy_plan = _rate(client_db, token, prop["id"], legacy["id"], code="LFLEX")
    annex = _property(client_db, token, name="Beach Annex")
    annex_room = _room(client_db, token, annex["id"], code="SUITE", name="Suite")
    annex_plan = _rate(client_db, token, annex["id"], annex_room["id"])
    _, admin = _platform_admin(client_db)
    campaign_id = _platform_campaign(client_db, admin, user["workspace"]["id"])[
        "campaign"
    ]["id"]

    # Only the parents are deactivated; the children stay active themselves.
    for path in (
        f"/api/v1/hotel/room-types/{legacy['id']}",
        f"/api/v1/hotel/properties/{annex['id']}",
    ):
        response = client_db.patch(path, headers=_auth(token), json={"active": False})
        assert response.status_code == 200, response.text

    def ids(kind, **params):
        data = _catalog(client_db, admin, campaign_id, kind=kind, **params).json()
        return {item["id"] for item in data["data"]["items"]}, data["data"]["total"]

    assert ids("room_type") == ({room["id"]}, 1)
    assert ids("rate_plan") == ({plan["id"]}, 1)
    assert ids("rate_plan", room_type_id=legacy["id"]) == (set(), 0)
    assert ids("rate_plan", property_id=annex["id"]) == (set(), 0)
    # active_only=false still lists everything for review.
    assert ids("room_type", active_only="false")[0] == {
        room["id"],
        legacy["id"],
        annex_room["id"],
    }
    assert ids("rate_plan", active_only="false")[0] == {
        plan["id"],
        legacy_plan["id"],
        annex_plan["id"],
    }
    # Still one audit event for the admin+campaign window.
    events = _audits(
        uuid.UUID(user["workspace"]["id"]), action="PLATFORM_CATALOG_VIEWED"
    )
    assert len(events) == 1


def test_targets_picked_from_catalog_create_a_labelled_rule(client_db):
    user, _, prop, room, plan = _setup(client_db)
    _, admin = _platform_admin(client_db)
    campaign_id = _platform_campaign(client_db, admin, user["workspace"]["id"])[
        "campaign"
    ]["id"]
    picked = {
        kind: [
            item["id"]
            for item in _catalog(client_db, admin, campaign_id, kind=kind).json()[
                "data"
            ]["items"]
        ]
        for kind in ("property", "room_type", "rate_plan")
    }
    response = client_db.post(
        f"{P}/campaigns/{campaign_id}/rules",
        headers=admin,
        json={
            "name": "Deluxe only",
            "discount_type": "PERCENTAGE",
            "discount_value": "10",
            "property_ids": picked["property"],
            "room_type_ids": picked["room_type"],
            "rate_plan_ids": picked["rate_plan"],
        }
        | _confirmed(),
    )
    assert response.status_code == 201, response.text
    detail = response.json()["data"]
    eligibility = detail["rules"][0]["eligibility"]
    assert eligibility["property_ids"] == [prop["id"]]
    assert eligibility["room_type_ids"] == [room["id"]]
    assert eligibility["rate_plan_ids"] == [plan["id"]]
    assert detail["target_labels"] == {
        prop["id"]: {"name": prop["name"], "active": True},
        room["id"]: {"name": room["name"], "active": True},
        plan["id"]: {"name": plan["name"], "active": True},
    }


def _set_campaign_status(campaign_id, status):
    async def write():
        async with TestSessionLocal() as session:
            await session.execute(
                update(PromotionCampaign)
                .where(PromotionCampaign.id == uuid.UUID(campaign_id))
                .values(status=status)
            )
            await session.commit()

    asyncio.run(write())


def test_catalog_reads_only_for_draft_campaign_in_active_workspace(client_db):
    user, _, prop, *_ = _setup(client_db)
    workspace_id = user["workspace"]["id"]
    _, admin = _platform_admin(client_db)
    campaign_id = _platform_campaign(client_db, admin, workspace_id)["campaign"]["id"]
    allowed = _catalog(client_db, admin, campaign_id, kind="property")
    assert allowed.status_code == 200, allowed.text
    assert [item["id"] for item in allowed.json()["data"]["items"]] == [prop["id"]]

    # Suspended Workspace: no catalog reads, and the denial is not audited as a view.
    suspended = client_db.post(
        f"/api/v1/platform/workspaces/{workspace_id}/suspend",
        headers=admin,
        json=_confirmed(),
    )
    assert suspended.status_code == 200, suspended.text
    denied = _catalog(client_db, admin, campaign_id, kind="property")
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "PLATFORM_CAMPAIGN_OPERATION_INVALID"
    assert denied.json()["error"]["details"]["reason_code"] == "WORKSPACE_NOT_ACTIVE"
    assert "items" not in (denied.json().get("data") or {})
    reactivated = client_db.post(
        f"/api/v1/platform/workspaces/{workspace_id}/reactivate",
        headers=admin,
        json=_confirmed(),
    )
    assert reactivated.status_code == 200, reactivated.text
    assert _catalog(client_db, admin, campaign_id, kind="property").status_code == 200

    # Rules can only be added to DRAFT campaigns, so other states cannot read.
    for status in ("ACTIVE", "PAUSED", "EXPIRED", "ARCHIVED"):
        _set_campaign_status(campaign_id, status)
        response = _catalog(client_db, admin, campaign_id, kind="rate_plan")
        assert response.status_code == 409, (status, response.text)
        assert response.json()["error"]["details"]["reason_code"] == (
            "CAMPAIGN_NOT_DRAFT"
        )
    events = _audits(uuid.UUID(workspace_id), action="PLATFORM_CATALOG_VIEWED")
    assert len(events) == 1  # only the first allowed read opened a window


def test_catalog_audit_is_one_event_per_admin_campaign_window(client_db, monkeypatch):
    user, _, *_ = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    first_admin, admin = _platform_admin(client_db)
    second_user, second_admin = _platform_admin(
        client_db, email="platform-2@example.com"
    )
    first_campaign = _platform_campaign(client_db, admin, str(workspace_id))[
        "campaign"
    ]["id"]
    second_campaign = _platform_campaign(
        client_db, admin, str(workspace_id), name="Second"
    )["campaign"]["id"]

    # Typing, paging, filtering and switching kinds stay in one window.
    for params in (
        {"kind": "property"},
        {"kind": "property", "search": "ab"},
        {"kind": "property", "search": "abc", "page": 2},
        {"kind": "room_type"},
        {"kind": "rate_plan", "active_only": "false"},
    ):
        response = _catalog(client_db, admin, first_campaign, **params)
        assert response.status_code == 200, response.text
    assert len(_audits(workspace_id, action="PLATFORM_CATALOG_VIEWED")) == 1

    # A different admin or a different campaign is a separate access.
    _catalog(client_db, second_admin, first_campaign, kind="property")
    _catalog(client_db, admin, second_campaign, kind="property")
    events = _audits(workspace_id, action="PLATFORM_CATALOG_VIEWED")
    assert len(events) == 3
    assert {
        (str(item.actor_user_id), item.safe_metadata["campaign_id"]) for item in events
    } == {
        (first_admin["id"], first_campaign),
        (second_user["id"], first_campaign),
        (first_admin["id"], second_campaign),
    }

    # Once the window has passed, the next read is audited again.
    monkeypatch.setattr(platform_campaign_module, "CATALOG_AUDIT_WINDOW", timedelta(0))
    _catalog(client_db, admin, first_campaign, kind="property")
    assert len(_audits(workspace_id, action="PLATFORM_CATALOG_VIEWED")) == 4
