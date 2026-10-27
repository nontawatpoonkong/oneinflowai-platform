"""Sprint 10.9F: platform campaign governance, scheduled lifecycle processing,
staff manual-booking quotes, and campaign analytics."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, update

import app.automation.worker as worker_module
from app.core.config import Settings
from app.models.audit import WorkspaceAuditEvent
from app.models.booking import Booking, BookingStatus
from app.models.hotel import InventoryDate
from app.models.promotion import (
    BookingAttribution,
    PromotionCampaign,
    PromotionRedemption,
    PromotionSource,
)
from app.models.scheduled_job import ScheduledJobState
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.promotion import PromotionValidationRequest
from app.services.promotion import PromotionRejectedError, PromotionService
from app.services.promotion_lifecycle import JOB_NAME, PromotionLifecycleService
from app.services.workspace_capability import WorkspaceCapability
from tests.conftest import TestSessionLocal
from tests.test_booking import _hold, _payload, _setup
from tests.test_crm import _customer
from tests.test_hotel import _auth, _property
from tests.test_platform_admin import _confirmed, _platform_admin
from tests.test_promotions import _promotion

P = "/api/v1/platform/marketing"


def _quote(prop, room, plan, **changes):
    return {
        "property_id": prop["id"],
        "room_type_id": room["id"],
        "rate_plan_id": plan["id"],
        "check_in": "2030-01-01",
        "check_out": "2030-01-04",
        "adults": 2,
        "children": 0,
        "quantity": 1,
        **changes,
    }


def _platform_campaign(client, admin_headers, workspace_id, **changes):
    response = client.post(
        f"{P}/campaigns",
        headers=admin_headers,
        json={"workspace_id": workspace_id, "name": "Platform Spring", **changes}
        | _confirmed("Partner marketing request #42"),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _audits(workspace_id, **filters):
    async def read():
        async with TestSessionLocal() as session:
            statement = select(WorkspaceAuditEvent).where(
                WorkspaceAuditEvent.workspace_id == workspace_id
            )
            for key, value in filters.items():
                statement = statement.where(getattr(WorkspaceAuditEvent, key) == value)
            return list(await session.scalars(statement))

    return asyncio.run(read())


def _set_window(campaign_id, *, valid_from=None, valid_until=None, **values):
    async def write():
        async with TestSessionLocal() as session:
            await session.execute(
                update(PromotionCampaign)
                .where(PromotionCampaign.id == uuid.UUID(campaign_id))
                .values(valid_from=valid_from, valid_until=valid_until, **values)
            )
            await session.commit()

    asyncio.run(write())


def _process(now=None, batch_size=100, worker_id="test-worker"):
    async def run():
        async with TestSessionLocal() as session:
            return await PromotionLifecycleService(session).process_due(
                now=now, batch_size=batch_size, worker_id=worker_id
            )

    return asyncio.run(run())


def _job_state():
    async def read():
        async with TestSessionLocal() as session:
            return await session.get(ScheduledJobState, JOB_NAME)

    return asyncio.run(read())


# --------------------------------------------------------------- authorization


def test_platform_campaign_routes_require_platform_admin(client_db):
    user, token, *_ = _setup(client_db)
    workspace_id = user["workspace"]["id"]
    owner = _auth(token)
    for method, path, body in (
        ("get", f"{P}/campaigns", None),
        ("get", f"{P}/analytics", None),
        ("get", f"{P}/lifecycle", None),
        ("get", f"{P}/campaigns/{uuid.uuid4()}", None),
        (
            "post",
            f"{P}/campaigns",
            {"workspace_id": workspace_id, "name": "x"} | _confirmed(),
        ),
    ):
        response = getattr(client_db, method)(
            path, headers=owner, **({"json": body} if body else {})
        )
        # Workspace OWNER never inherits platform authority.
        assert response.status_code == 403, (path, response.text)
        assert response.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"


# ------------------------------------------------------------------ governance


def test_platform_authors_workspace_owned_draft_with_audited_reason(client_db):
    user, token, prop, room, plan = _setup(client_db)
    workspace_id = user["workspace"]["id"]
    _, admin = _platform_admin(client_db)

    detail = _platform_campaign(client_db, admin, workspace_id)
    campaign = detail["campaign"]
    assert campaign["status"] == "DRAFT"
    assert campaign["origin"] == "PLATFORM"
    assert detail["funding"]["discount_borne_by"] == "WORKSPACE"
    assert detail["funding"]["platform_funded"] is False
    assert "activate" not in detail["allowed_operations"]

    detail = client_db.post(
        f"{P}/campaigns/{campaign['id']}/rules",
        headers=admin,
        json={
            "name": "Spring 15",
            "discount_type": "PERCENTAGE",
            "discount_value": "15.00",
            "property_ids": [prop["id"]],
            "sources": ["MANUAL"],
            # Body campaign_id is ignored; the path is authoritative.
            "campaign_id": str(uuid.uuid4()),
        }
        | _confirmed("Add spring rule"),
    )
    assert detail.status_code == 201, detail.text
    rule = detail.json()["data"]["rules"][0]
    assert rule["eligibility"]["property_ids"] == [prop["id"]]

    detail = client_db.post(
        f"{P}/campaigns/{campaign['id']}/codes",
        headers=admin,
        json={"promotion_id": rule["id"], "code": "spring15", "usage_limit": 5}
        | _confirmed("Issue spring code"),
    )
    assert detail.status_code == 201, detail.text
    code = detail.json()["data"]["codes"][0]
    assert code["code"] == "SPRING15"
    assert code["effective_limit"] == 5
    assert code["remaining"] == 5

    # Workspace staff see the platform-authored draft in their own list.
    listed = client_db.get("/api/v1/promotions/campaigns", headers=_auth(token))
    assert listed.json()["data"][0]["management_origin"] == "PLATFORM"

    # A DRAFT authored by the platform never discounts anything.
    preview = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json={
            "code": "SPRING15",
            "property_id": prop["id"],
            "room_type_id": room["id"],
            "rate_plan_id": plan["id"],
            "check_in": "2030-01-01",
            "check_out": "2030-01-04",
            "subtotal": "1000.00",
            "currency": "THB",
            "source": "MANUAL",
        },
    ).json()["data"]
    assert preview["valid"] is False
    assert preview["reason_code"] == "PROMOTION_INACTIVE"

    events = _audits(uuid.UUID(workspace_id), actor_type="PLATFORM_ADMIN")
    assert {event.action for event in events} == {
        "PROMOTION_CAMPAIGN_CREATED",
        "PROMOTION_CREATED",
        "PROMOTION_CODE_CREATED",
    }
    assert all(event.safe_metadata.get("reason") for event in events)
    history = client_db.get(f"{P}/campaigns/{campaign['id']}", headers=admin).json()
    assert len(history["data"]["audit"]) == 3


def test_platform_cannot_activate_resume_or_reenable(client_db):
    user, token, prop, room, plan = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    campaign, _, code = _promotion(client_db, token, prop, room, plan)
    _, admin = _platform_admin(client_db)

    for verb in ("activate", "resume"):
        assert client_db.post(
            f"{P}/campaigns/{campaign['id']}/{verb}",
            headers=admin,
            json=_confirmed(),
        ).status_code in {404, 405}
    paused = client_db.post(
        f"{P}/campaigns/{campaign['id']}/pause", headers=admin, json=_confirmed()
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["data"]["status"] == "PAUSED"
    # Repeating the same operation is idempotent and does not re-audit.
    again = client_db.post(
        f"{P}/campaigns/{campaign['id']}/pause", headers=admin, json=_confirmed()
    )
    assert again.status_code == 200
    assert len(_audits(workspace_id, action="PROMOTION_CAMPAIGN_PAUSED")) == 1

    disabled = client_db.post(
        f"{P}/codes/{code['id']}/disable", headers=admin, json=_confirmed()
    )
    assert disabled.status_code == 200
    assert client_db.post(
        f"{P}/codes/{code['id']}/enable", headers=admin, json=_confirmed()
    ).status_code in {404, 405}

    archived = client_db.post(
        f"{P}/campaigns/{campaign['id']}/archive", headers=admin, json=_confirmed()
    )
    assert archived.json()["data"]["status"] == "ARCHIVED"
    # Previously the platform path bypassed the state machine (ARCHIVED -> PAUSED).
    reopened = client_db.post(
        f"{P}/campaigns/{campaign['id']}/pause", headers=admin, json=_confirmed()
    )
    assert reopened.status_code == 409
    assert reopened.json()["error"]["code"] == "PROMOTION_TRANSITION_INVALID"

    # The owning Workspace keeps its own resume/enable authority.
    workspace_code = client_db.post(
        f"/api/v1/promotions/codes/{code['id']}/enable", headers=_auth(token)
    )
    assert workspace_code.status_code == 200
    assert workspace_code.json()["data"]["status"] == "ACTIVE"
    enabled = _audits(workspace_id, action="PROMOTION_CODE_ENABLED")
    assert len(enabled) == 1 and enabled[0].actor_type == "USER"


def test_platform_edits_and_additions_follow_lifecycle_rules(client_db):
    user, token, prop, *_ = _setup(client_db)
    _, admin = _platform_admin(client_db)
    detail = _platform_campaign(client_db, admin, user["workspace"]["id"])
    campaign_id = detail["campaign"]["id"]
    later = (datetime.now(UTC) + timedelta(days=30)).isoformat()

    draft_edit = client_db.patch(
        f"{P}/campaigns/{campaign_id}",
        headers=admin,
        json={"valid_until": later, "name": "Renamed"} | _confirmed(),
    )
    assert draft_edit.status_code == 200, draft_edit.text
    assert draft_edit.json()["data"]["campaign"]["name"] == "Renamed"

    rule = client_db.post(
        f"{P}/campaigns/{campaign_id}/rules",
        headers=admin,
        json={"name": "R", "discount_type": "PERCENTAGE", "discount_value": "5"}
        | _confirmed(),
    ).json()["data"]["rules"][0]
    activated = client_db.post(
        f"/api/v1/promotions/campaigns/{campaign_id}/activate", headers=_auth(token)
    )
    assert activated.status_code == 200
    assert activated.json()["data"]["started_at"] is not None

    live_window = client_db.patch(
        f"{P}/campaigns/{campaign_id}",
        headers=admin,
        json={"valid_until": None} | _confirmed(),
    )
    assert live_window.status_code == 409
    assert live_window.json()["error"]["details"]["fields"] == ["valid_until"]
    live_name = client_db.patch(
        f"{P}/campaigns/{campaign_id}",
        headers=admin,
        json={"description": "Clarified terms"} | _confirmed(),
    )
    assert live_name.status_code == 200
    late_code = client_db.post(
        f"{P}/campaigns/{campaign_id}/codes",
        headers=admin,
        json={"promotion_id": rule["id"], "code": "LATE"} | _confirmed(),
    )
    assert late_code.status_code == 409
    assert late_code.json()["error"]["code"] == "PLATFORM_CAMPAIGN_OPERATION_INVALID"

    missing_reason = client_db.post(
        f"{P}/campaigns/{campaign_id}/expire",
        headers=admin,
        json={"reason": "  ", "confirmed": True},
    )
    assert missing_reason.status_code == 422
    expired = client_db.post(
        f"{P}/campaigns/{campaign_id}/expire", headers=admin, json=_confirmed()
    )
    assert expired.json()["data"]["status"] == "EXPIRED"


def test_platform_rule_rejects_other_workspace_catalog(client_db):
    user, _, _, _, _ = _setup(client_db)
    _, other_token, other_prop, *_ = _setup(client_db, email="other-owner@example.com")
    _, admin = _platform_admin(client_db)
    detail = _platform_campaign(client_db, admin, user["workspace"]["id"])
    response = client_db.post(
        f"{P}/campaigns/{detail['campaign']['id']}/rules",
        headers=admin,
        json={
            "name": "Cross",
            "discount_type": "PERCENTAGE",
            "discount_value": "10",
            "property_ids": [other_prop["id"]],
        }
        | _confirmed(),
    )
    # The domain rejects foreign targets before the composite FKs fire.
    assert response.status_code == 422
    assert response.json()["error"]["details"]["reason_code"] == (
        "PROMOTION_TARGET_INVALID"
    )
    del other_token


def test_platform_lists_search_and_paginate(client_db):
    user, token, prop, room, plan = _setup(client_db)
    for code in ("ALPHA1", "ALPHA2", "BETA1"):
        _promotion(client_db, token, prop, room, plan, code=code)
    _, admin = _platform_admin(client_db)
    page = client_db.get(f"{P}/campaigns?page_size=2", headers=admin).json()["data"]
    assert page["total"] == 3 and len(page["items"]) == 2 and page["total_pages"] == 2
    found = client_db.get(f"{P}/codes?search=alp", headers=admin).json()["data"]
    assert sorted(item["code"] for item in found["items"]) == ["ALPHA1", "ALPHA2"]
    wildcard = client_db.get(f"{P}/codes?search=%25", headers=admin).json()["data"]
    assert wildcard["total"] == 0
    named = client_db.get(f"{P}/campaigns?search=BETA", headers=admin).json()["data"]
    assert [item["name"] for item in named["items"]] == ["Campaign BETA1"]
    bounded = client_db.get(f"{P}/campaigns?page_size=101", headers=admin)
    assert bounded.status_code == 422


# ------------------------------------------------------------------- scheduler


def test_scheduled_lifecycle_expires_and_starts_once(client_db):
    user, token, prop, room, plan = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    ending, _, _ = _promotion(client_db, token, prop, room, plan, code="ENDING")
    starting, _, _ = _promotion(client_db, token, prop, room, plan, code="STARTING")
    now = datetime.now(UTC)
    _set_window(
        ending["id"],
        valid_from=now - timedelta(days=2),
        valid_until=now - timedelta(minutes=1),
    )
    _set_window(starting["id"], valid_from=now - timedelta(minutes=1), started_at=None)

    # Validity is enforced even before the scheduler has run.
    preview = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json={
            "code": "ENDING",
            "property_id": prop["id"],
            "room_type_id": room["id"],
            "rate_plan_id": plan["id"],
            "check_in": "2030-01-01",
            "check_out": "2030-01-04",
            "subtotal": "1000.00",
            "currency": "THB",
            "source": "MANUAL",
        },
    ).json()["data"]
    assert preview["reason_code"] == "PROMOTION_EXPIRED"

    first = _process()
    assert (first["expired"], first["started"]) == (1, 1)
    second = _process()
    assert (second["expired"], second["started"]) == (0, 0)

    expired = _audits(workspace_id, action="PROMOTION_CAMPAIGN_EXPIRED")
    started = _audits(workspace_id, action="PROMOTION_CAMPAIGN_STARTED")
    assert len(expired) == 1 and len(started) == 1
    assert expired[0].actor_type == "AUTOMATION"
    assert expired[0].safe_metadata["trigger"] == "SCHEDULED"
    state = _job_state()
    assert state.total_runs == 2
    assert state.total_processed == 2
    assert state.consecutive_failures == 0
    assert state.last_worker_id == "test-worker"

    statuses = client_db.get(
        "/api/v1/promotions/campaigns", headers=_auth(token)
    ).json()["data"]
    by_id = {item["id"]: item for item in statuses}
    assert by_id[ending["id"]]["status"] == "EXPIRED"
    assert by_id[starting["id"]]["started_at"] is not None


def test_scheduled_lifecycle_concurrent_workers_transition_once(client_db):
    user, token, prop, room, plan = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    campaigns = [
        _promotion(client_db, token, prop, room, plan, code=f"C{index}")[0]
        for index in range(4)
    ]
    now = datetime.now(UTC)
    for campaign in campaigns:
        _set_window(
            campaign["id"],
            valid_from=now - timedelta(days=1),
            valid_until=now - timedelta(seconds=5),
        )

    async def race():
        async def worker(name):
            async with TestSessionLocal() as session:
                return await PromotionLifecycleService(session).process_due(
                    batch_size=2, worker_id=name
                )

        return await asyncio.gather(*(worker(f"w{i}") for i in range(4)))

    results = asyncio.run(race())
    assert sum(item["expired"] for item in results) <= 4
    # Drain anything skipped while locked, then verify exactly-once transitions.
    while _process(batch_size=2)["expired"]:
        pass
    assert len(_audits(workspace_id, action="PROMOTION_CAMPAIGN_EXPIRED")) == 4
    assert _job_state().total_failures == 0


def test_scheduled_lifecycle_failure_is_observable_and_recovers(client_db, monkeypatch):
    async def broken(self, now, limit):
        raise RuntimeError("SELECT secret FROM somewhere")

    original = PromotionLifecycleService._expire_due
    monkeypatch.setattr(PromotionLifecycleService, "_expire_due", broken)
    with pytest.raises(RuntimeError):
        _process()
    state = _job_state()
    assert state.consecutive_failures == 1
    assert state.last_error_code == "RuntimeError"
    assert "secret" not in json.dumps({"code": state.last_error_code}, default=str)

    async def status():
        async with TestSessionLocal() as session:
            return await PromotionLifecycleService(session).status(
                stale_after_seconds=300
            )

    report = asyncio.run(status())
    assert report["health"] == "NOT_RUNNING"
    assert "LIFECYCLE_FAILING" in report["alerts"]

    monkeypatch.setattr(PromotionLifecycleService, "_expire_due", original)
    _process()
    state = _job_state()
    assert state.consecutive_failures == 0
    assert state.total_failures == 1
    assert asyncio.run(status())["health"] == "HEALTHY"


def test_worker_runs_lifecycle_phase_and_isolates_failures(client_db, monkeypatch):
    monkeypatch.setattr(worker_module, "AsyncSessionLocal", TestSessionLocal)
    settings = Settings(_env_file=None, PROMOTION_LIFECYCLE_INTERVAL_SECONDS=30)
    delay = asyncio.run(worker_module.run_promotion_lifecycle_once("w", settings))
    assert delay == 30.0
    assert _job_state().total_runs == 1

    async def broken(self, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(PromotionLifecycleService, "process_due", broken)
    delay = asyncio.run(worker_module.run_promotion_lifecycle_once("w", settings))
    assert delay == 30.0  # failure is logged and retried next interval


@pytest.mark.parametrize(
    "overrides",
    [
        {"PROMOTION_LIFECYCLE_INTERVAL_SECONDS": 1},
        {"PROMOTION_LIFECYCLE_BATCH_SIZE": 0},
        {"PROMOTION_LIFECYCLE_BATCH_SIZE": 501},
        {
            "PROMOTION_LIFECYCLE_INTERVAL_SECONDS": 200,
            "PROMOTION_LIFECYCLE_STALE_SECONDS": 300,
        },
    ],
)
def test_lifecycle_settings_reject_impossible_values(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


# --------------------------------------------------------------- manual booking


def _redemption_count(workspace_id):
    async def read():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(func.count())
                .select_from(PromotionRedemption)
                .where(PromotionRedemption.workspace_id == workspace_id)
            )

    return asyncio.run(read())


def _reserved_units(workspace_id):
    async def read():
        async with TestSessionLocal() as session:
            return list(
                await session.scalars(
                    select(InventoryDate.reserved_units).where(
                        InventoryDate.workspace_id == workspace_id
                    )
                )
            )

    return asyncio.run(read())


def test_manual_quote_matches_hold_and_reserves_nothing(client_db):
    user, token, prop, room, plan = _setup(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _promotion(client_db, token, prop, room, plan)
    customer = _customer(client_db, token)

    quote = client_db.post(
        "/api/v1/hotel/bookings/manual-quote",
        headers=_auth(token),
        json=_quote(
            prop,
            room,
            plan,
            customer_id=customer["id"],
            promotion_code="welcome10",
        ),
    )
    assert quote.status_code == 200, quote.text
    data = quote.json()["data"]
    assert data["available"] is True
    assert data["authoritative"] is False
    assert data["currency"] == "THB"
    assert [rate["amount"] for rate in data["nightly_rates"]] == ["1500.25"] * 3
    assert (data["subtotal"], data["discount_amount"], data["total"]) == (
        "4500.75",
        "450.08",
        "4050.67",
    )
    assert data["promotion"]["valid"] is True
    # Previewing reserves no inventory and consumes no promotion quota.
    assert set(_reserved_units(workspace_id)) == {0}
    assert _redemption_count(workspace_id) == 0

    hold = _hold(
        client_db,
        token,
        _payload(
            prop,
            room,
            plan,
            key="manual-1",
            guest_name=None,
            customer_id=customer["id"],
            promotion_code="WELCOME10",
        ),
    )
    assert hold.status_code == 201, hold.text
    booking = hold.json()["data"]
    assert booking["status"] == "HELD"  # never CONFIRMED by staff creation
    assert (
        booking["subtotal"],
        booking["discount_amount"],
        booking["total_amount"],
    ) == (
        data["subtotal"],
        data["discount_amount"],
        data["total"],
    )
    assert set(_reserved_units(workspace_id)) == {1}

    async def read():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(BookingAttribution).where(
                    BookingAttribution.booking_id == uuid.UUID(booking["id"])
                )
            )

    assert asyncio.run(read()).source is PromotionSource.MANUAL
    held = _audits(workspace_id, action="BOOKING_HELD")
    assert held[0].safe_metadata == {
        "quantity": 1,
        "source": "STAFF",
        "promotion_applied": True,
    }

    retry = _hold(
        client_db,
        token,
        _payload(
            prop,
            room,
            plan,
            key="manual-1",
            guest_name=None,
            customer_id=customer["id"],
            promotion_code="WELCOME10",
        ),
    )
    assert retry.json()["data"]["id"] == booking["id"]
    assert _redemption_count(workspace_id) == 1


def test_manual_quote_reports_stable_reasons(client_db):
    _, token, prop, room, plan = _setup(client_db)
    url = "/api/v1/hotel/bookings/manual-quote"

    def post(**changes):
        response = client_db.post(
            url, headers=_auth(token), json=_quote(prop, room, plan, **changes)
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    assert post(adults=50)["reason_code"] == "OCCUPANCY_EXCEEDED"
    insufficient = post(quantity=2)
    assert insufficient["reason_code"] == "INSUFFICIENT_UNITS"
    assert insufficient["available_units"] == 1
    assert post(check_in="2031-01-01", check_out="2031-01-02")["reason_code"] == (
        "NOT_AVAILABLE"
    )
    unknown = post(promotion_code="NOPE")
    assert unknown["available"] is True
    assert unknown["promotion"] == {
        "valid": False,
        "reason_code": "PROMOTION_NOT_FOUND",
        "code": None,
        "promotion_name": None,
        "discount_type": None,
        "discount_value": None,
    }
    assert unknown["discount_amount"] == "0.00"
    malformed = post(promotion_code="bad code!")
    assert malformed["promotion"]["reason_code"] == "PROMOTION_NOT_FOUND"
    invalid = client_db.post(
        url,
        headers=_auth(token),
        json=_quote(prop, room, plan, check_out="2029-12-31"),
    )
    assert invalid.status_code == 422


def test_manual_quote_requires_booking_create_and_isolates_workspaces(client_db):
    user, token, prop, room, plan = _setup(client_db)
    other_user, other_token, *_ = _setup(client_db, email="other-owner@example.com")
    del other_user
    url = "/api/v1/hotel/bookings/manual-quote"

    foreign = client_db.post(
        url, headers=_auth(other_token), json=_quote(prop, room, plan)
    )
    assert foreign.status_code == 404
    other_prop = _property(client_db, other_token)
    mixed = client_db.post(
        url,
        headers=_auth(token),
        json=_quote(prop, room, plan) | {"property_id": other_prop["id"]},
    )
    assert mixed.status_code == 404

    workspace_id = uuid.UUID(user["workspace"]["id"])

    async def grant_booking_create_only():
        async with TestSessionLocal() as session:
            member = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == uuid.UUID(user["user"]["id"]),
                )
            )
            member.role = WorkspaceRole.MEMBER
            session.add(
                WorkspaceMemberCapability(
                    workspace_id=workspace_id,
                    membership_id=member.id,
                    capability=WorkspaceCapability.BOOKING_CREATE.value,
                    granted_by_user_id=uuid.UUID(user["user"]["id"]),
                    granted_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(grant_booking_create_only())
    denied_quote = client_db.post(
        url, headers=_auth(token), json=_quote(prop, room, plan)
    )
    assert denied_quote.status_code == 403
    denied_hold = _hold(
        client_db, token, _payload(prop, room, plan, key="no-room-read")
    )
    assert denied_hold.status_code == 403


# ------------------------------------------------------------------- analytics


def _confirm_booking(workspace_id, booking_id):
    async def write():
        async with TestSessionLocal() as session:
            await session.execute(
                update(Booking)
                .where(Booking.id == booking_id)
                .values(status=BookingStatus.CONFIRMED)
            )
            await PromotionService(session).confirm_redemption(workspace_id, booking_id)
            await session.commit()

    asyncio.run(write())


def test_campaign_analytics_platform_and_workspace(client_db):
    user, token, prop, room, plan = _setup(client_db, units=2)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _promotion(client_db, token, prop, room, plan)
    first = _hold(
        client_db,
        token,
        _payload(prop, room, plan, key="a", promotion_code="WELCOME10"),
    ).json()["data"]
    second = _hold(
        client_db,
        token,
        _payload(prop, room, plan, key="b", promotion_code="WELCOME10"),
    ).json()["data"]
    _confirm_booking(workspace_id, uuid.UUID(first["id"]))
    cancelled = client_db.post(
        f"/api/v1/hotel/bookings/{second['id']}/cancel", headers=_auth(token)
    )
    assert cancelled.status_code == 200, cancelled.text

    _, admin = _platform_admin(client_db)
    response = client_db.get(f"{P}/analytics", headers=admin)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["campaigns_by_status"]["ACTIVE"] == 1
    assert data["codes_by_status"]["ACTIVE"] == 1
    assert data["validations"]["available"] is False
    assert data["campaign_cost"]["available"] is False
    funnel = data["reservation_funnel"]
    assert (funnel["reserved"], funnel["confirmed"], funnel["released"]) == (2, 1, 1)
    assert data["confirmed_by_currency"] == [
        {
            "currency": "THB",
            "redemptions": 1,
            "gross_amount": "4500.75",
            "discount_granted": "450.08",
            "net_amount": "4050.67",
        }
    ]
    assert len(data["daily_trend"]) == 1
    assert data["daily_trend"][0]["discount_granted"] == "450.08"
    assert data["top_workspaces"][0]["workspace_id"] == str(workspace_id)
    assert data["by_source"][0]["source"] == "MANUAL"
    assert "health" in data["lifecycle"]

    naive = client_db.get(f"{P}/analytics?start=2030-01-01T00:00:00", headers=admin)
    assert naive.status_code == 422
    too_long = client_db.get(
        f"{P}/analytics?start=2020-01-01T00:00:00Z&end=2030-01-01T00:00:00Z",
        headers=admin,
    )
    assert too_long.status_code == 422

    overview = client_db.get("/api/v1/analytics/overview", headers=_auth(token))
    assert overview.status_code == 200, overview.text
    promotions = overview.json()["data"]["sales"]["promotions"]
    assert promotions["reservation_funnel"]["reserved"] == 2
    assert promotions["reservation_funnel"]["confirmed"] == 1
    assert promotions["campaigns_by_status"]["ACTIVE"] == 1
    assert promotions["daily_trend"][0]["uses"] == 1
    assert promotions["properties"][0]["label"] == prop["name"]

    # Another Workspace sees none of this Workspace's campaign data.
    _, other_token, *_ = _setup(client_db, email="other-owner@example.com")
    other = client_db.get(
        "/api/v1/analytics/overview", headers=_auth(other_token)
    ).json()["data"]["sales"]["promotions"]
    assert other["reservation_funnel"]["reserved"] == 0
    assert other["campaigns_by_status"]["ACTIVE"] == 0
    assert other["daily_trend"] == []


def test_platform_campaign_payloads_exclude_secrets(client_db):
    user, token, prop, room, plan = _setup(client_db)
    campaign, _, _ = _promotion(client_db, token, prop, room, plan)
    _hold(client_db, token, _payload(prop, room, plan, promotion_code="WELCOME10"))
    _, admin = _platform_admin(client_db)
    bodies = [
        client_db.get(f"{P}/campaigns/{campaign['id']}", headers=admin).text,
        client_db.get(f"{P}/campaigns", headers=admin).text,
        client_db.get(f"{P}/codes", headers=admin).text,
        client_db.get(f"{P}/analytics", headers=admin).text,
    ]
    for body in bodies:
        lowered = body.lower()
        for fragment in ("password", "token", "hashed", "secret", "guest_name"):
            assert fragment not in lowered, fragment
    del user


# ------------------------------------------------- audit-round regressions


def _second_code(client, token, rule_id, code, usage_limit=None):
    response = client.post(
        "/api/v1/promotions/codes",
        headers=_auth(token),
        json={"promotion_id": rule_id, "code": code, "usage_limit": usage_limit},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_total_quota_is_serialized_across_codes_of_one_rule(client_db):
    """Two codes share one rule. Locking only the code row let a second code
    count usage before the first reservation committed and exceed the limit."""

    user, token, prop, room, plan = _setup(client_db, units=2)
    _, rule, _ = _promotion(client_db, token, prop, room, plan, total_usage_limit=1)
    _second_code(client_db, token, rule["id"], "SECOND")
    workspace_id = uuid.UUID(user["workspace"]["id"])
    first = _hold(client_db, token, _payload(prop, room, plan, key="x1")).json()
    second = _hold(client_db, token, _payload(prop, room, plan, key="x2")).json()

    def request(code):
        return PromotionValidationRequest(
            code=code,
            property_id=prop["id"],
            room_type_id=room["id"],
            rate_plan_id=plan["id"],
            check_in="2030-01-01",
            check_out="2030-01-04",
            subtotal="4500.75",
            currency="THB",
            source="MANUAL",
        )

    async def scenario():
        expires = datetime.now(UTC) + timedelta(minutes=15)
        async with TestSessionLocal() as holder, TestSessionLocal() as contender:
            await PromotionService(holder).reserve_for_booking(
                workspace_id=workspace_id,
                booking_id=uuid.UUID(first["data"]["id"]),
                customer_id=None,
                hold_expires_at=expires,
                data=request("WELCOME10"),
            )  # uncommitted: the reservation and its locks are still held

            async def contend():
                try:
                    await PromotionService(contender).reserve_for_booking(
                        workspace_id=workspace_id,
                        booking_id=uuid.UUID(second["data"]["id"]),
                        customer_id=None,
                        hold_expires_at=expires,
                        data=request("SECOND"),
                    )
                    await contender.commit()
                    return "RESERVED"
                except PromotionRejectedError as exc:
                    await contender.rollback()
                    return exc.details["reason_code"]

            task = asyncio.create_task(contend())
            await asyncio.sleep(1.0)
            blocked = not task.done()
            await holder.commit()
            return blocked, await task

    blocked, outcome = asyncio.run(scenario())
    assert blocked, "second code must wait for the rule-level quota lock"
    assert outcome == "PROMOTION_USAGE_LIMIT_REACHED"
    assert _redemption_count(workspace_id) == 1


def test_code_usage_limit_counts_only_that_code(client_db):
    _, token, prop, room, plan = _setup(client_db, units=3)
    _, rule, first = _promotion(client_db, token, prop, room, plan)
    first_limited = client_db.post(
        f"/api/v1/promotions/codes/{first['id']}/archive", headers=_auth(token)
    )
    assert first_limited.status_code == 200
    _second_code(client_db, token, rule["id"], "CODEA", usage_limit=1)
    _second_code(client_db, token, rule["id"], "CODEB", usage_limit=1)

    a = _hold(
        client_db, token, _payload(prop, room, plan, key="a1", promotion_code="CODEA")
    )
    assert a.status_code == 201, a.text
    again = _hold(
        client_db, token, _payload(prop, room, plan, key="a2", promotion_code="CODEA")
    )
    assert again.status_code == 422
    assert again.json()["error"]["details"]["reason_code"] == (
        "PROMOTION_USAGE_LIMIT_REACHED"
    )
    # CODEB has its own limit; CODEA's use must not exhaust it.
    b = _hold(
        client_db, token, _payload(prop, room, plan, key="b1", promotion_code="CODEB")
    )
    assert b.status_code == 201, b.text

    _, admin = _platform_admin(client_db)
    codes = client_db.get(f"{P}/codes?search=CODE", headers=admin).json()["data"]
    remaining = {item["code"]: item["remaining"] for item in codes["items"]}
    assert remaining == {"CODEA": 0, "CODEB": 0}


def test_workspace_rule_rejects_foreign_catalog_targets_cleanly(client_db):
    _, token, *_ = _setup(client_db)
    _, other_token, other_prop, other_room, other_plan = _setup(
        client_db, email="other-owner@example.com"
    )
    del other_token
    campaign = client_db.post(
        "/api/v1/promotions/campaigns", headers=_auth(token), json={"name": "Mine"}
    ).json()["data"]
    for field, value in (
        ("property_ids", other_prop["id"]),
        ("room_type_ids", other_room["id"]),
        ("rate_plan_ids", other_plan["id"]),
    ):
        response = client_db.post(
            "/api/v1/promotions",
            headers=_auth(token),
            json={
                "campaign_id": campaign["id"],
                "name": "Foreign",
                "discount_type": "PERCENTAGE",
                "discount_value": "10",
                field: [value],
            },
        )
        assert response.status_code == 422, (field, response.text)
        assert response.json()["error"]["details"]["reason_code"] == (
            "PROMOTION_TARGET_INVALID"
        )


def test_campaign_update_rejects_explicit_null_name(client_db):
    user, token, *_ = _setup(client_db)
    campaign = client_db.post(
        "/api/v1/promotions/campaigns", headers=_auth(token), json={"name": "Keep"}
    ).json()["data"]
    response = client_db.patch(
        f"/api/v1/promotions/campaigns/{campaign['id']}",
        headers=_auth(token),
        json={"name": None},
    )
    assert response.status_code == 422
    _, admin = _platform_admin(client_db)
    platform = client_db.patch(
        f"{P}/campaigns/{campaign['id']}",
        headers=admin,
        json={"name": None} | _confirmed(),
    )
    assert platform.status_code == 422
    del user


def test_platform_marketing_money_is_serialized_as_decimal_strings(client_db):
    user, token, prop, room, plan = _setup(client_db)
    _promotion(client_db, token, prop, room, plan)
    booking = _hold(
        client_db, token, _payload(prop, room, plan, promotion_code="WELCOME10")
    ).json()["data"]
    _confirm_booking(uuid.UUID(user["workspace"]["id"]), uuid.UUID(booking["id"]))
    _, admin = _platform_admin(client_db)

    attribution = client_db.get(f"{P}/attribution", headers=admin).json()["data"]
    row = attribution["items"][0]
    assert (row["gross_value"], row["discount"], row["net_value"]) == (
        "4500.75",
        "450.08",
        "4050.67",
    )
    analytics = client_db.get("/api/v1/platform/analytics", headers=admin).json()[
        "data"
    ]
    assert analytics["hotel_booking_value"][0]["value"] == "4050.67"


def test_reserve_and_confirm_share_lock_order_without_deadlock(client_db):
    """Confirm locks redemption -> rule. Reserve must not take the rule lock
    before touching lapsed redemptions, or the two paths can deadlock."""

    user, token, prop, room, plan = _setup(client_db, units=2)
    _promotion(client_db, token, prop, room, plan)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    first = _hold(
        client_db,
        token,
        _payload(prop, room, plan, key="lapse-1", promotion_code="WELCOME10"),
    ).json()["data"]
    second = _hold(client_db, token, _payload(prop, room, plan, key="lapse-2"))
    second = second.json()["data"]
    first_id = uuid.UUID(first["id"])

    async def lapse():
        async with TestSessionLocal() as session:
            await session.execute(
                update(PromotionRedemption)
                .where(PromotionRedemption.booking_id == first_id)
                .values(reserved_until=datetime.now(UTC) - timedelta(minutes=1))
            )
            await session.commit()

    asyncio.run(lapse())

    async def scenario():
        async with TestSessionLocal() as confirmer, TestSessionLocal() as holder:
            # Confirm's first step: lock the (lapsed) redemption row.
            await confirmer.execute(
                select(PromotionRedemption.id)
                .where(PromotionRedemption.booking_id == first_id)
                .with_for_update()
            )

            async def reserve():
                await PromotionService(holder).reserve_for_booking(
                    workspace_id=workspace_id,
                    booking_id=uuid.UUID(second["id"]),
                    customer_id=None,
                    hold_expires_at=datetime.now(UTC) + timedelta(minutes=15),
                    data=PromotionValidationRequest(
                        code="WELCOME10",
                        property_id=prop["id"],
                        room_type_id=room["id"],
                        rate_plan_id=plan["id"],
                        check_in="2030-01-01",
                        check_out="2030-01-04",
                        subtotal="4500.75",
                        currency="THB",
                        source="MANUAL",
                    ),
                )
                await holder.commit()

            task = asyncio.create_task(reserve())
            await asyncio.sleep(0.5)  # holder is now waiting on a lock
            # Confirm's second step: the rule lock. With the inverted order the
            # holder already owns it and PostgreSQL aborts one side.
            await PromotionService(confirmer).confirm_redemption(workspace_id, first_id)
            await confirmer.commit()
            await task

    asyncio.run(scenario())
    assert _redemption_count(workspace_id) == 2
