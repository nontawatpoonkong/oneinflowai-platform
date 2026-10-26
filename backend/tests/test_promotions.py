"""PostgreSQL-backed promotion, attribution, and booking-price tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update

from app.models.audit import WorkspaceAuditEvent
from app.models.booking import Booking
from app.models.promotion import (
    BookingAttribution,
    PromotionCode,
    PromotionCodeStatus,
    PromotionRedemption,
    PromotionRedemptionStatus,
    PromotionSource,
)
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.booking import BookingHoldCreate
from app.schemas.promotion import PromotionValidationRequest
from app.services.booking import BookingService
from app.services.promotion import (
    PromotionRejectedError,
    PromotionService,
)
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_booking import _hold, _payload, _setup
from tests.test_crm import _customer
from tests.test_hotel import _auth
from tests.test_payments import _destination


def _promotion(
    client,
    token,
    prop,
    room,
    plan,
    *,
    code="WELCOME10",
    discount_type="PERCENTAGE",
    discount_value="10.00",
    **changes,
):
    campaign = client.post(
        "/api/v1/promotions/campaigns",
        headers=_auth(token),
        json={"name": f"Campaign {code}"},
    )
    assert campaign.status_code == 201, campaign.text
    campaign = campaign.json()["data"]
    payload = {
        "campaign_id": campaign["id"],
        "name": f"Rule {code}",
        "discount_type": discount_type,
        "discount_value": discount_value,
        "currency": "THB" if discount_type == "FIXED_AMOUNT" else None,
        "property_ids": [prop["id"]],
        "room_type_ids": [room["id"]],
        "rate_plan_ids": [plan["id"]],
        "sources": ["MANUAL"],
        **changes,
    }
    rule = client.post("/api/v1/promotions", headers=_auth(token), json=payload)
    assert rule.status_code == 201, rule.text
    rule = rule.json()["data"]
    promotion_code = client.post(
        "/api/v1/promotions/codes",
        headers=_auth(token),
        json={
            "promotion_id": rule["id"],
            "code": code,
            "usage_limit": changes.get("total_usage_limit"),
        },
    )
    assert promotion_code.status_code == 201, promotion_code.text
    promotion_code = promotion_code.json()["data"]
    activated = client.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/activate",
        headers=_auth(token),
    )
    assert activated.status_code == 200, activated.text
    return campaign, rule, promotion_code


def _validation(prop, room, plan, **changes):
    return {
        "code": "WELCOME10",
        "property_id": prop["id"],
        "room_type_id": room["id"],
        "rate_plan_id": plan["id"],
        "check_in": "2030-01-01",
        "check_out": "2030-01-04",
        "subtotal": "4500.75",
        "currency": "THB",
        "source": "MANUAL",
        **changes,
    }


def test_percentage_code_freezes_discount_and_attribution_on_hold(client_db):
    user, token, prop, room, plan = _setup(client_db)
    campaign, rule, code = _promotion(client_db, token, prop, room, plan)

    response = _hold(
        client_db,
        token,
        _payload(prop, room, plan, promotion_code="welcome10"),
    )
    assert response.status_code == 201, response.text
    booking = response.json()["data"]
    assert booking["subtotal"] == "4500.75"
    assert booking["discount_amount"] == "450.08"
    assert booking["total_amount"] == "4050.67"
    assert booking["promotion_snapshot"] == {
        "promotion_id": rule["id"],
        "campaign_id": campaign["id"],
        "promotion_code_id": code["id"],
        "code": "WELCOME10",
        "promotion_name": "Rule WELCOME10",
        "discount_type": "PERCENTAGE",
        "discount_value": "10.00",
        "discount_amount": "450.08",
        "frozen": True,
    }

    async def read():
        async with TestSessionLocal() as session:
            attribution = await session.scalar(
                select(BookingAttribution).where(
                    BookingAttribution.booking_id == uuid.UUID(booking["id"])
                )
            )
            redemption = await session.scalar(
                select(PromotionRedemption).where(
                    PromotionRedemption.booking_id == uuid.UUID(booking["id"])
                )
            )
            return attribution, redemption

    attribution, redemption = asyncio.run(read())
    assert attribution.workspace_id == uuid.UUID(user["workspace"]["id"])
    assert attribution.source is PromotionSource.MANUAL
    assert str(attribution.campaign_id) == campaign["id"]
    assert redemption.status is PromotionRedemptionStatus.RESERVED
    assert redemption.discount_amount == Decimal("450.08")


def test_fixed_discount_cap_minimum_and_decimal_rounding(client_db):
    _, token, prop, room, plan = _setup(client_db)
    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        code="FIXED",
        discount_type="FIXED_AMOUNT",
        discount_value="500.00",
        minimum_subtotal="4000.00",
    )
    fixed = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan, code="fixed"),
    ).json()["data"]
    assert fixed["valid"] is True
    assert fixed["discount_amount"] == "500.00"
    assert fixed["final_total"] == "4000.75"

    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        code="CAP",
        discount_value="33.33",
        max_discount_amount="100.00",
    )
    capped = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan, code="CAP"),
    ).json()["data"]
    assert capped["discount_amount"] == "100.00"
    assert capped["final_total"] == "4400.75"

    too_small = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan, code="FIXED", subtotal="3999.99"),
    ).json()["data"]
    assert too_small["valid"] is False
    assert too_small["reason_code"] == "PROMOTION_MINIMUM_NOT_MET"
    assert too_small["discount_amount"] == "0.00"


def test_campaign_lifecycle_and_workspace_isolation(client_db):
    _, token, prop, room, plan = _setup(client_db, email="promo-a@example.com")
    campaign, _, code = _promotion(client_db, token, prop, room, plan)
    paused = client_db.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/pause",
        headers=_auth(token),
    )
    assert paused.status_code == 200
    invalid = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan),
    ).json()["data"]
    assert invalid["reason_code"] == "PROMOTION_INACTIVE"
    assert (
        _hold(
            client_db,
            token,
            _payload(prop, room, plan, promotion_code="WELCOME10"),
        ).status_code
        == 422
    )

    _, other_token = register_verify_and_login(client_db, email="promo-b@example.com")
    assert (
        client_db.get(
            "/api/v1/promotions/campaigns", headers=_auth(other_token)
        ).json()["data"]
        == []
    )
    foreign = client_db.post(
        f"/api/v1/promotions/codes/{code['id']}/disable",
        headers=_auth(other_token),
    )
    assert foreign.status_code == 404


def test_quota_is_reserved_at_hold_and_released_on_cancel(client_db):
    _, token, prop, room, plan = _setup(client_db, units=2)
    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        total_usage_limit=1,
    )
    first = _hold(
        client_db,
        token,
        _payload(prop, room, plan, key="promo-first", promotion_code="WELCOME10"),
    )
    assert first.status_code == 201
    blocked = _hold(
        client_db,
        token,
        _payload(prop, room, plan, key="promo-second", promotion_code="WELCOME10"),
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["details"]["reason_code"] == (
        "PROMOTION_USAGE_LIMIT_REACHED"
    )
    booking_id = first.json()["data"]["id"]
    assert (
        client_db.post(
            f"/api/v1/hotel/bookings/{booking_id}/cancel", headers=_auth(token)
        ).status_code
        == 200
    )
    retried = _hold(
        client_db,
        token,
        _payload(prop, room, plan, key="promo-third", promotion_code="WELCOME10"),
    )
    assert retried.status_code == 201, retried.text


def test_expired_hold_releases_quota_and_new_hold_revalidates(client_db):
    user, token, prop, room, plan = _setup(client_db)
    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        total_usage_limit=1,
    )
    first = _hold(
        client_db,
        token,
        _payload(prop, room, plan, key="promo-expiring", promotion_code="WELCOME10"),
    )
    assert first.status_code == 201, first.text

    async def expire():
        async with TestSessionLocal() as session:
            await session.execute(
                update(Booking)
                .where(Booking.id == uuid.UUID(first.json()["data"]["id"]))
                .values(hold_expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
            count = await BookingService(session).expire_due_holds(
                uuid.UUID(user["workspace"]["id"])
            )
            redemption = await session.scalar(
                select(PromotionRedemption).where(
                    PromotionRedemption.booking_id
                    == uuid.UUID(first.json()["data"]["id"])
                )
            )
            return count, redemption.status

    assert asyncio.run(expire()) == (1, PromotionRedemptionStatus.RELEASED)
    retried = _hold(
        client_db,
        token,
        _payload(
            prop,
            room,
            plan,
            key="promo-after-expiry",
            promotion_code="WELCOME10",
        ),
    )
    assert retried.status_code == 201, retried.text
    assert retried.json()["data"]["discount_amount"] == "450.08"


def test_booking_retry_does_not_duplicate_promotion_redemption(client_db):
    user, token, prop, room, plan = _setup(client_db)
    _promotion(client_db, token, prop, room, plan)
    payload = _payload(prop, room, plan, promotion_code="WELCOME10")
    first = _hold(client_db, token, payload)
    second = _hold(client_db, token, payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]

    async def count():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(func.count())
                .select_from(PromotionRedemption)
                .where(
                    PromotionRedemption.workspace_id
                    == uuid.UUID(user["workspace"]["id"])
                )
            )

    assert asyncio.run(count()) == 1


def test_concurrent_last_promotion_quota_has_one_hold_winner(client_db):
    user, token, prop, room, plan = _setup(client_db, units=2)
    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        total_usage_limit=1,
    )
    workspace_id = uuid.UUID(user["workspace"]["id"])
    actor_id = uuid.UUID(user["user"]["id"])

    async def contend(key):
        async with TestSessionLocal() as session:
            request = BookingHoldCreate.model_validate(
                _payload(
                    prop,
                    room,
                    plan,
                    key=key,
                    promotion_code="WELCOME10",
                )
            )
            try:
                booking = await BookingService(session).create_hold(
                    workspace_id, actor_id, request
                )
                return booking.id
            except PromotionRejectedError:
                return None

    async def run():
        return await asyncio.gather(contend("quota-race-a"), contend("quota-race-b"))

    winners = asyncio.run(run())
    assert sum(value is not None for value in winners) == 1

    async def counts():
        async with TestSessionLocal() as session:
            bookings = await session.scalar(
                select(func.count())
                .select_from(Booking)
                .where(Booking.workspace_id == workspace_id)
            )
            redemptions = await session.scalar(
                select(func.count())
                .select_from(PromotionRedemption)
                .where(PromotionRedemption.workspace_id == workspace_id)
            )
            return bookings, redemptions

    assert asyncio.run(counts()) == (1, 1)


def test_validation_is_source_and_catalog_scoped(client_db):
    user, token, prop, room, plan = _setup(client_db)
    _promotion(client_db, token, prop, room, plan)
    wrong_source = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan, source="WEBCHAT"),
    ).json()["data"]
    assert wrong_source["reason_code"] == "PROMOTION_SOURCE_NOT_ELIGIBLE"

    async def validate(request):
        async with TestSessionLocal() as session:
            return await PromotionService(session).validate(
                uuid.UUID(user["workspace"]["id"]),
                request,
            )

    for field, reason in (
        ("property_id", "PROMOTION_PROPERTY_NOT_ELIGIBLE"),
        ("room_type_id", "PROMOTION_ROOM_TYPE_NOT_ELIGIBLE"),
        ("rate_plan_id", "PROMOTION_RATE_PLAN_NOT_ELIGIBLE"),
    ):
        request = PromotionValidationRequest.model_validate(
            _validation(prop, room, plan, **{field: str(uuid.uuid4())})
        )
        assert asyncio.run(validate(request)).reason_code == reason


def test_not_started_expired_and_archived_codes_have_stable_reasons(client_db):
    _, token, prop, room, plan = _setup(client_db)
    _, _, expired_code = _promotion(client_db, token, prop, room, plan, code="OLD")
    _, _, archived_code = _promotion(
        client_db, token, prop, room, plan, code="ARCHIVED"
    )
    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        code="FUTURE",
        valid_from="2099-01-01T00:00:00Z",
    )

    async def set_statuses():
        async with TestSessionLocal() as session:
            await session.execute(
                update(PromotionCode)
                .where(PromotionCode.id == uuid.UUID(expired_code["id"]))
                .values(status=PromotionCodeStatus.EXPIRED)
            )
            await session.execute(
                update(PromotionCode)
                .where(PromotionCode.id == uuid.UUID(archived_code["id"]))
                .values(status=PromotionCodeStatus.ARCHIVED)
            )
            await session.commit()

    asyncio.run(set_statuses())
    for code, reason in (
        ("OLD", "PROMOTION_EXPIRED"),
        ("ARCHIVED", "PROMOTION_INACTIVE"),
        ("FUTURE", "PROMOTION_NOT_STARTED"),
    ):
        result = client_db.post(
            "/api/v1/promotions/validate",
            headers=_auth(token),
            json=_validation(prop, room, plan, code=code),
        ).json()["data"]
        assert result["valid"] is False
        assert result["reason_code"] == reason


def test_code_lifecycle_duplicate_and_invalid_transition(client_db):
    _, token, prop, room, plan = _setup(client_db)
    campaign, rule, code = _promotion(client_db, token, prop, room, plan)
    duplicate = client_db.post(
        "/api/v1/promotions/codes",
        headers=_auth(token),
        json={"promotion_id": rule["id"], "code": "welcome10"},
    )
    assert duplicate.status_code == 409

    disabled = client_db.post(
        f"/api/v1/promotions/codes/{code['id']}/disable", headers=_auth(token)
    )
    assert disabled.status_code == 200
    invalid = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan),
    ).json()["data"]
    assert invalid["reason_code"] == "PROMOTION_INACTIVE"
    archived = client_db.post(
        f"/api/v1/promotions/codes/{code['id']}/archive", headers=_auth(token)
    )
    assert archived.status_code == 200
    assert client_db.post(
        f"/api/v1/promotions/codes/{code['id']}/disable", headers=_auth(token)
    ).status_code == 409
    assert client_db.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/archive",
        headers=_auth(token),
    ).status_code == 200
    assert client_db.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/activate",
        headers=_auth(token),
    ).status_code == 409


def test_repeated_lifecycle_transition_is_noop_without_duplicate_audit(client_db):
    user, token, prop, room, plan = _setup(client_db)
    campaign, _, code = _promotion(client_db, token, prop, room, plan)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    calls = [
        (f"/api/v1/promotions/campaigns/{campaign['id']}/pause", "PAUSED"),
        (f"/api/v1/promotions/codes/{code['id']}/disable", "DISABLED"),
    ]
    for path, status in calls:
        first = client_db.post(path, headers=_auth(token))
        assert first.status_code == 200, first.text
        repeated = client_db.post(path, headers=_auth(token))
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["data"]["status"] == status
        assert repeated.json()["data"]["updated_at"] == first.json()["data"][
            "updated_at"
        ]

    async def count(action):
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(func.count())
                .select_from(WorkspaceAuditEvent)
                .where(
                    WorkspaceAuditEvent.workspace_id == workspace_id,
                    WorkspaceAuditEvent.action == action,
                )
            )

    assert asyncio.run(count("PROMOTION_CAMPAIGN_PAUSED")) == 1
    assert asyncio.run(count("PROMOTION_CODE_DISABLED")) == 1

    # Same-status no-op never relaxes the state machine for other targets.
    assert client_db.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/archive",
        headers=_auth(token),
    ).status_code == 200
    assert client_db.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/archive",
        headers=_auth(token),
    ).status_code == 200
    rejected = client_db.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/pause",
        headers=_auth(token),
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "PROMOTION_TRANSITION_INVALID"


def test_eligibility_stay_currency_and_discount_floor(client_db):
    _, token, prop, room, plan = _setup(client_db)
    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        code="DATES",
        stay_date_start="2030-02-01",
        stay_date_end="2030-02-28",
    )
    outside = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan, code="DATES"),
    ).json()["data"]
    assert outside["reason_code"] == "PROMOTION_STAY_DATE_NOT_ELIGIBLE"

    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        code="BIG",
        discount_type="FIXED_AMOUNT",
        discount_value="9999.00",
    )
    floor = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan, code="BIG", subtotal="50.00"),
    ).json()["data"]
    assert floor["discount_amount"] == "50.00"
    assert floor["final_total"] == "0.00"
    currency = client_db.post(
        "/api/v1/promotions/validate",
        headers=_auth(token),
        json=_validation(prop, room, plan, code="BIG", currency="USD"),
    ).json()["data"]
    assert currency["reason_code"] == "PROMOTION_CURRENCY_MISMATCH"


def test_quote_is_informational_and_hold_revalidates_paused_campaign(client_db):
    _, token, prop, room, plan = _setup(client_db)
    campaign, _, _ = _promotion(client_db, token, prop, room, plan)
    draft = client_db.post(
        "/api/v1/hotel/bookings/draft",
        headers=_auth(token),
        json=_payload(prop, room, plan, key="promo-draft", promotion_code="WELCOME10"),
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["data"]["promotion_snapshot"]["frozen"] is False
    assert client_db.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/pause",
        headers=_auth(token),
    ).status_code == 200
    hold = client_db.post(
        f"/api/v1/hotel/bookings/{draft.json()['data']['id']}/hold",
        headers=_auth(token),
    )
    assert hold.status_code == 422
    assert hold.json()["error"]["details"]["reason_code"] == "PROMOTION_INACTIVE"


def test_frozen_booking_and_payment_keep_discount_after_rule_edit(client_db):
    user, token, prop, room, plan = _setup(client_db)
    campaign, rule, _ = _promotion(client_db, token, prop, room, plan)
    held = _hold(
        client_db,
        token,
        _payload(prop, room, plan, promotion_code="WELCOME10"),
    )
    assert held.status_code == 201, held.text
    booking = held.json()["data"]
    changed = client_db.patch(
        f"/api/v1/promotions/rules/{rule['id']}",
        headers=_auth(token),
        json={"discount_value": "50.00"},
    )
    assert changed.status_code == 200, changed.text
    assert client_db.post(
        f"/api/v1/promotions/campaigns/{campaign['id']}/pause",
        headers=_auth(token),
    ).status_code == 200
    stored = client_db.get(
        f"/api/v1/hotel/bookings/{booking['id']}", headers=_auth(token)
    ).json()["data"]
    assert stored["discount_amount"] == "450.08"
    assert stored["total_amount"] == "4050.67"
    assert stored["promotion_snapshot"]["discount_value"] == "10.00"

    assert client_db.post(
        f"/api/v1/hotel/bookings/{booking['id']}/advance-to-payment",
        headers=_auth(token),
    ).status_code == 200
    destination_id = _destination(client_db, _auth(token))
    payment = client_db.post(
        f"/api/v1/hotel/bookings/{booking['id']}/payment",
        headers=_auth(token),
        json={"payment_destination_id": destination_id},
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["data"]["expected_amount"] == "4050.67"

    async def confirm_frozen_reservation():
        async with TestSessionLocal() as session:
            redemption = await PromotionService(session).confirm_redemption(
                uuid.UUID(user["workspace"]["id"]), uuid.UUID(booking["id"])
            )
            await session.commit()
            return redemption.status

    assert asyncio.run(confirm_frozen_reservation()) == (
        PromotionRedemptionStatus.CONFIRMED
    )


def test_redemption_confirmation_is_idempotent_and_audited(client_db):
    user, token, prop, room, plan = _setup(client_db)
    _promotion(client_db, token, prop, room, plan)
    booking = _hold(
        client_db,
        token,
        _payload(prop, room, plan, promotion_code="WELCOME10"),
    ).json()["data"]
    workspace_id = uuid.UUID(user["workspace"]["id"])
    booking_id = uuid.UUID(booking["id"])

    async def confirm():
        async with TestSessionLocal() as session:
            service = PromotionService(session)
            first = await service.confirm_redemption(workspace_id, booking_id)
            second = await service.confirm_redemption(workspace_id, booking_id)
            await session.commit()
            count = await session.scalar(
                select(func.count())
                .select_from(PromotionRedemption)
                .where(PromotionRedemption.booking_id == booking_id)
            )
            actions = set(
                await session.scalars(
                    select(WorkspaceAuditEvent.action).where(
                        WorkspaceAuditEvent.workspace_id == workspace_id
                    )
                )
            )
            return first.id, second.id, count, actions

    first_id, second_id, count, actions = asyncio.run(confirm())
    assert first_id == second_id
    assert count == 1
    assert {
        "PROMOTION_CAMPAIGN_CREATED",
        "PROMOTION_CAMPAIGN_ACTIVATED",
        "PROMOTION_CREATED",
        "PROMOTION_CODE_CREATED",
        "PROMOTION_APPLIED",
        "PROMOTION_REDEMPTION_CONFIRMED",
    } <= actions


def test_per_customer_limit_counts_confirmed_redemption(client_db):
    user, token, prop, room, plan = _setup(client_db, units=2)
    customer = _customer(client_db, token, "Promo Guest")
    _promotion(
        client_db,
        token,
        prop,
        room,
        plan,
        per_customer_limit=1,
    )
    first = _hold(
        client_db,
        token,
        _payload(
            prop,
            room,
            plan,
            key="customer-limit-a",
            customer_id=customer["id"],
            promotion_code="WELCOME10",
        ),
    )
    assert first.status_code == 201, first.text

    async def confirm():
        async with TestSessionLocal() as session:
            await PromotionService(session).confirm_redemption(
                uuid.UUID(user["workspace"]["id"]),
                uuid.UUID(first.json()["data"]["id"]),
            )
            await session.commit()

    asyncio.run(confirm())
    second = _hold(
        client_db,
        token,
        _payload(
            prop,
            room,
            plan,
            key="customer-limit-b",
            customer_id=customer["id"],
            promotion_code="WELCOME10",
        ),
    )
    assert second.status_code == 422
    assert second.json()["error"]["details"]["reason_code"] == (
        "PROMOTION_CUSTOMER_LIMIT_REACHED"
    )


def test_member_read_grant_does_not_allow_promotion_management(client_db):
    user, token, prop, room, plan = _setup(client_db)
    _promotion(client_db, token, prop, room, plan)
    workspace_id = uuid.UUID(user["workspace"]["id"])

    async def demote_and_grant_read():
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
                    capability="promotion.read",
                    granted_by_user_id=uuid.UUID(user["user"]["id"]),
                        granted_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(demote_and_grant_read())
    assert client_db.get(
        "/api/v1/promotions/campaigns", headers=_auth(token)
    ).status_code == 200
    denied = client_db.post(
        "/api/v1/promotions/campaigns",
        headers=_auth(token),
        json={"name": "Denied"},
    )
    assert denied.status_code == 403
