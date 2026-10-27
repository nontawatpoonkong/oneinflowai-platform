"""Manual quote must agree with the Hold on rate plan / property currency."""

import asyncio
import uuid

from sqlalchemy import update

from app.models.hotel import RatePlan
from tests.conftest import TestSessionLocal
from tests.test_booking import _hold, _payload, _setup
from tests.test_hotel import _auth


def _set_plan_currency(plan_id, currency):
    # The catalog API rejects mismatched currencies, so drift is simulated
    # directly in the database (e.g. legacy data or an out-of-band change).
    async def write():
        async with TestSessionLocal() as session:
            await session.execute(
                update(RatePlan)
                .where(RatePlan.id == uuid.UUID(plan_id))
                .values(currency=currency)
            )
            await session.commit()

    asyncio.run(write())


def test_manual_quote_rejects_rate_currency_mismatch_like_hold(client_db):
    _, token, prop, room, plan = _setup(client_db)
    assert prop["currency"] == "THB"
    _set_plan_currency(plan["id"], "USD")

    quote = client_db.post(
        "/api/v1/hotel/bookings/manual-quote",
        headers=_auth(token),
        json={
            "property_id": prop["id"],
            "room_type_id": room["id"],
            "rate_plan_id": plan["id"],
            "check_in": "2030-01-01",
            "check_out": "2030-01-04",
            "adults": 2,
            "children": 0,
            "quantity": 1,
        },
    )
    assert quote.status_code == 200, quote.text
    data = quote.json()["data"]
    assert data["available"] is False
    assert data["reason_code"] == "RATE_CURRENCY_MISMATCH"
    assert data["authoritative"] is False
    assert data["total"] is None
    assert data["nightly_rates"] == []

    # The Hold stays authoritative and rejects the same request.
    hold = _hold(client_db, token, _payload(prop, room, plan))
    assert hold.status_code == 422, hold.text
    assert hold.json()["error"]["code"] == "BOOKING_VALIDATION_ERROR"
