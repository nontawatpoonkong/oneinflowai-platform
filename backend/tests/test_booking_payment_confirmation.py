"""PostgreSQL-backed payment-to-booking confirmation safety tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.channels import ChannelType
from app.models.booking import Booking, BookingEvent, BookingEventType, BookingStatus
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.payment import Payment, PaymentStatus
from app.services.booking import BookingService, BookingTransitionError
from app.services.booking_payment_confirmation import (
    BookingPaymentConfirmationService,
    BookingPaymentError,
)
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_booking import _hold, _inventory_rows, _payload, _setup
from tests.test_hotel import _auth


def _prepared(client, *, email="booking-payment@example.com", draft=False, units=1):
    user, token, prop, room, plan = _setup(client, email=email, units=units)
    destination = client.post(
        "/api/v1/payments/destinations",
        headers=_auth(token),
        json={
            "type": "BANK_ACCOUNT",
            "display_name": "Hotel bank",
            "account_name": "OneInFlow Shop",
            "account_number_masked": "xxx-x-x1234-x",
        },
    )
    assert destination.status_code == 201, destination.text
    endpoint = (
        "/api/v1/hotel/bookings/draft" if draft else "/api/v1/hotel/bookings/hold"
    )
    booking_response = client.post(
        endpoint, headers=_auth(token), json=_payload(prop, room, plan)
    )
    assert booking_response.status_code == 201, booking_response.text
    booking = booking_response.json()["data"]
    return user, token, booking, destination.json()["data"]["id"], plan


def _advance(client, token, booking):
    response = client.post(
        f"/api/v1/hotel/bookings/{booking['id']}/advance-to-payment",
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text


def _link(client, token, booking, destination_id):
    return client.post(
        f"/api/v1/hotel/bookings/{booking['id']}/payment",
        headers=_auth(token),
        json={"payment_destination_id": destination_id},
    )


def _confirm(client, token, booking, payment_id):
    return client.post(
        f"/api/v1/hotel/bookings/{booking['id']}/confirm-from-payment",
        headers=_auth(token),
        json={"payment_id": payment_id},
    )


def _mark_verified(
    payment_id, *, amount=None, currency=None, status=PaymentStatus.VERIFIED
):
    async def run():
        async with TestSessionLocal() as session:
            payment = await session.get(Payment, uuid.UUID(payment_id))
            payment.status = status
            payment.verified_amount = (
                amount if amount is not None else payment.expected_amount
            )
            payment.verified_at = datetime.now(UTC)
            if currency is not None:
                payment.currency = currency
            await session.commit()

    asyncio.run(run())


def _state(workspace_id, booking_id, payment_id):
    async def run():
        async with TestSessionLocal() as session:
            booking = await session.get(Booking, uuid.UUID(booking_id))
            payment = await session.get(Payment, uuid.UUID(payment_id))
            events = list(
                (
                    await session.execute(
                        select(BookingEvent).where(
                            BookingEvent.workspace_id == workspace_id,
                            BookingEvent.booking_id == booking.id,
                        )
                    )
                ).scalars()
            )
            return booking, payment, events

    return asyncio.run(run())


def test_verified_payment_confirms_snapshot_once_and_preserves_inventory(client_db):
    user, token, booking, destination_id, plan = _prepared(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _advance(client_db, token, booking)
    linked = _link(client_db, token, booking, destination_id)
    assert linked.status_code == 201, linked.text
    payment = linked.json()["data"]
    assert payment["booking_id"] == booking["id"]
    assert payment["expected_amount"] == booking["total_amount"]
    assert payment["currency"] == booking["currency"]
    assert payment["booking_applied_at"] is None
    repeat_link = _link(client_db, token, booking, destination_id)
    assert repeat_link.json()["data"]["id"] == payment["id"]
    changed = client_db.patch(
        f"/api/v1/hotel/rate-plans/{plan['id']}",
        headers=_auth(token),
        json={"base_price": "9999.99"},
    )
    assert changed.status_code == 200
    _mark_verified(payment["id"])
    first = _confirm(client_db, token, booking, payment["id"])
    second = _confirm(client_db, token, booking, payment["id"])
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["status"] == "CONFIRMED"
    assert second.json()["data"]["status"] == "CONFIRMED"
    assert first.json()["data"]["hold_expires_at"] is None
    saved_booking, saved_payment, events = _state(
        workspace_id, booking["id"], payment["id"]
    )
    assert saved_booking.total_amount == Decimal("4500.75")
    assert saved_payment.booking_applied_at is not None
    assert [e.event_type for e in events].count(BookingEventType.PAYMENT_LINKED) == 1
    confirmed = [
        e for e in events if e.event_type == BookingEventType.BOOKING_CONFIRMED
    ]
    assert len(confirmed) == 1
    assert confirmed[0].event_metadata == {"payment_id": payment["id"]}
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}

    async def expire_due():
        async with TestSessionLocal() as session:
            return await BookingService(session).expire_due_holds(
                workspace_id, now=datetime.now(UTC) + timedelta(days=1)
            )

    assert asyncio.run(expire_due()) == 0
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}


@pytest.mark.parametrize(
    "mutation",
    [
        "unverified",
        "rejected",
        "wrong_expected",
        "wrong_verified",
        "wrong_currency",
        "expired",
    ],
)
def test_confirmation_rejects_invalid_payment_without_consuming(client_db, mutation):
    user, token, booking, destination_id, _ = _prepared(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _advance(client_db, token, booking)
    payment_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]
    if mutation == "rejected":
        _mark_verified(payment_id, status=PaymentStatus.REJECTED)
    elif mutation != "unverified":
        _mark_verified(payment_id)

    async def alter():
        async with TestSessionLocal() as session:
            payment = await session.get(Payment, uuid.UUID(payment_id))
            booking_row = await session.get(Booking, uuid.UUID(booking["id"]))
            if mutation == "wrong_expected":
                payment.expected_amount += Decimal("1.00")
            elif mutation == "wrong_verified":
                payment.verified_amount += Decimal("1.00")
            elif mutation == "wrong_currency":
                payment.currency = "USD"
            elif mutation == "expired":
                booking_row.hold_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(alter())
    response = _confirm(client_db, token, booking, payment_id)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "BOOKING_PAYMENT_INVALID"
    saved_booking, saved_payment, events = _state(
        workspace_id, booking["id"], payment_id
    )
    assert saved_booking.status == BookingStatus.PENDING_PAYMENT
    assert saved_payment.booking_applied_at is None
    assert all(e.event_type != BookingEventType.BOOKING_CONFIRMED for e in events)
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}


@pytest.mark.parametrize("state", ["DRAFT", "HELD", "CANCELLED", "EXPIRED"])
def test_non_pending_booking_cannot_initiate_payment(client_db, state):
    _, token, booking, destination_id, _ = _prepared(client_db, draft=state == "DRAFT")
    if state == "CANCELLED":
        assert (
            client_db.post(
                f"/api/v1/hotel/bookings/{booking['id']}/cancel", headers=_auth(token)
            ).status_code
            == 200
        )
    elif state == "EXPIRED":

        async def expire():
            async with TestSessionLocal() as session:
                await BookingService(session).expire(
                    uuid.UUID(booking["workspace_id"]),
                    uuid.UUID(booking["id"]),
                    now=datetime.now(UTC) + timedelta(minutes=16),
                )

        asyncio.run(expire())
    result = _link(client_db, token, booking, destination_id)
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "BOOKING_PAYMENT_INVALID"


def test_cross_workspace_and_wrong_booking_payment_rejected(client_db):
    _, token, booking, destination_id, _ = _prepared(client_db, units=2)
    _advance(client_db, token, booking)
    payment_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]
    _mark_verified(payment_id)
    _, other_token = register_verify_and_login(
        client_db, email="other-booking-payment@example.com"
    )
    other_response = _confirm(client_db, other_token, booking, payment_id)
    assert other_response.status_code == 404
    item = booking["item"]
    wrong_booking = _hold(
        client_db,
        token,
        _payload(
            {"id": booking["property_id"]},
            {"id": item["room_type_id"]},
            {"id": item["rate_plan_id"]},
            key="second-payment-booking",
        ),
    )
    assert wrong_booking.status_code == 201, wrong_booking.text
    _advance(client_db, token, wrong_booking.json()["data"])
    assert (
        _confirm(client_db, token, wrong_booking.json()["data"], payment_id).status_code
        == 409
    )
    unrelated = client_db.post(
        "/api/v1/payments",
        headers=_auth(token),
        json={
            "payment_destination_id": destination_id,
            "expected_amount": booking["total_amount"],
            "currency": booking["currency"],
        },
    )
    assert unrelated.status_code == 201, unrelated.text
    unrelated_id = unrelated.json()["data"]["id"]
    _mark_verified(unrelated_id)
    invalid = _confirm(client_db, token, booking, unrelated_id)
    assert invalid.status_code == 409
    assert _confirm(client_db, token, booking, payment_id).status_code == 200


def test_concurrent_confirmation_and_expiry_have_one_winner(client_db):
    user, token, booking, destination_id, _ = _prepared(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    booking_id = uuid.UUID(booking["id"])
    actor_id = uuid.UUID(user["user"]["id"])
    _advance(client_db, token, booking)
    payment_id = uuid.UUID(
        _link(client_db, token, booking, destination_id).json()["data"]["id"]
    )
    _mark_verified(str(payment_id))

    async def confirm():
        async with TestSessionLocal() as session:
            return await BookingPaymentConfirmationService(session).confirm(
                workspace_id, booking_id, payment_id, actor_id
            )

    async def expire():
        async with TestSessionLocal() as session:
            return await BookingService(session).expire(
                workspace_id,
                booking_id,
                now=datetime.now(UTC) + timedelta(minutes=16),
            )

    async def run():
        return await asyncio.gather(confirm(), expire(), return_exceptions=True)

    results = asyncio.run(run())
    assert sum(not isinstance(value, Exception) for value in results) == 1
    assert any(
        isinstance(value, (BookingPaymentError, BookingTransitionError))
        for value in results
    )
    saved_booking, saved_payment, events = _state(
        workspace_id, str(booking_id), str(payment_id)
    )
    assert saved_booking.status in {BookingStatus.CONFIRMED, BookingStatus.EXPIRED}
    assert (saved_payment.booking_applied_at is not None) == (
        saved_booking.status == BookingStatus.CONFIRMED
    )
    assert [e.event_type for e in events].count(BookingEventType.BOOKING_CONFIRMED) <= 1
    assert {count for _, count in _inventory_rows(workspace_id)} == (
        {1} if saved_booking.status == BookingStatus.CONFIRMED else {0}
    )


def test_simultaneous_confirmation_is_single_application(client_db):
    user, token, booking, destination_id, _ = _prepared(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    booking_id = uuid.UUID(booking["id"])
    actor_id = uuid.UUID(user["user"]["id"])
    _advance(client_db, token, booking)
    payment_id = uuid.UUID(
        _link(client_db, token, booking, destination_id).json()["data"]["id"]
    )
    _mark_verified(str(payment_id))

    async def one():
        async with TestSessionLocal() as session:
            return (
                await BookingPaymentConfirmationService(session).confirm(
                    workspace_id, booking_id, payment_id, actor_id
                )
            ).id

    async def run():
        return await asyncio.gather(one(), one())

    assert asyncio.run(run()) == [booking_id, booking_id]
    _, payment, events = _state(workspace_id, str(booking_id), str(payment_id))
    assert payment.booking_applied_at is not None
    assert [e.event_type for e in events].count(BookingEventType.BOOKING_CONFIRMED) == 1
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}


def test_confirmation_commit_failure_rolls_back_marker_state_and_event(
    client_db, monkeypatch
):
    user, token, booking, destination_id, _ = _prepared(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _advance(client_db, token, booking)
    payment_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]
    _mark_verified(payment_id)

    async def run():
        async with TestSessionLocal() as session:

            async def fail_after_flush():
                await session.flush()
                raise RuntimeError("injected commit failure")

            monkeypatch.setattr(session, "commit", fail_after_flush)
            with pytest.raises(RuntimeError, match="injected commit failure"):
                await BookingPaymentConfirmationService(session).confirm(
                    workspace_id,
                    uuid.UUID(booking["id"]),
                    uuid.UUID(payment_id),
                    uuid.UUID(user["user"]["id"]),
                )

    asyncio.run(run())
    saved_booking, saved_payment, events = _state(
        workspace_id, booking["id"], payment_id
    )
    assert saved_booking.status == BookingStatus.PENDING_PAYMENT
    assert saved_payment.booking_applied_at is None
    assert all(e.event_type != BookingEventType.BOOKING_CONFIRMED for e in events)


def test_database_enforces_booking_workspace_and_single_applied_payment(client_db):
    first, token, booking, destination_id, _ = _prepared(client_db)
    _advance(client_db, token, booking)
    payment_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]
    second, second_token = register_verify_and_login(
        client_db, email="booking-payment-foreign@example.com"
    )
    foreign_workspace = uuid.UUID(second["workspace"]["id"])
    foreign_destination = client_db.post(
        "/api/v1/payments/destinations",
        headers=_auth(second_token),
        json={"type": "BANK_ACCOUNT", "display_name": "Other bank"},
    )
    assert foreign_destination.status_code == 201
    foreign_destination_id = uuid.UUID(foreign_destination.json()["data"]["id"])

    async def check():
        async with TestSessionLocal() as session:
            session.add(
                Payment(
                    workspace_id=foreign_workspace,
                    booking_id=uuid.UUID(booking["id"]),
                    payment_destination_id=foreign_destination_id,
                    expected_amount=Decimal("4500.75"),
                    currency="THB",
                    status=PaymentStatus.PENDING,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
            original = await session.get(Payment, uuid.UUID(payment_id))
            second_attempt = Payment(
                workspace_id=uuid.UUID(first["workspace"]["id"]),
                booking_id=uuid.UUID(booking["id"]),
                payment_destination_id=original.payment_destination_id,
                expected_amount=original.expected_amount,
                currency=original.currency,
                status=PaymentStatus.PENDING,
            )
            session.add(second_attempt)
            await session.commit()
            original.booking_applied_at = datetime.now(UTC)
            second_attempt.booking_applied_at = datetime.now(UTC)
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(check())


def test_booking_payment_preserves_customer_conversation_links(client_db):
    user, token, booking, destination_id, _ = _prepared(client_db, units=2)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    customer_id, conversation_id = uuid.uuid4(), uuid.uuid4()

    async def seed():
        async with TestSessionLocal() as session:
            session.add(
                Customer(
                    id=customer_id, workspace_id=workspace_id, display_name="Guest"
                )
            )
            session.add(
                Conversation(
                    id=conversation_id,
                    workspace_id=workspace_id,
                    customer_id=customer_id,
                    channel=ChannelType.WEB,
                )
            )
            await session.commit()

    asyncio.run(seed())
    item = booking["item"]
    linked_booking = _hold(
        client_db,
        token,
        _payload(
            {"id": booking["property_id"]},
            {"id": item["room_type_id"]},
            {"id": item["rate_plan_id"]},
            key="customer-linked",
            customer_id=str(customer_id),
            conversation_id=str(conversation_id),
        ),
    )
    assert linked_booking.status_code == 201, linked_booking.text
    linked_booking = linked_booking.json()["data"]
    _advance(client_db, token, linked_booking)
    payment = _link(client_db, token, linked_booking, destination_id)
    assert payment.status_code == 201, payment.text
    assert payment.json()["data"]["customer_id"] == str(customer_id)
    assert payment.json()["data"]["conversation_id"] == str(conversation_id)


@pytest.mark.parametrize("ending", ["cancel", "expire"])
def test_linked_payment_cannot_confirm_cancelled_or_expired_booking(client_db, ending):
    user, token, booking, destination_id, _ = _prepared(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _advance(client_db, token, booking)
    payment_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]
    _mark_verified(payment_id)
    if ending == "cancel":
        response = client_db.post(
            f"/api/v1/hotel/bookings/{booking['id']}/cancel", headers=_auth(token)
        )
        assert response.status_code == 200, response.text
    else:

        async def expire():
            async with TestSessionLocal() as session:
                return await BookingService(session).expire(
                    workspace_id,
                    uuid.UUID(booking["id"]),
                    now=datetime.now(UTC) + timedelta(minutes=16),
                )

        assert asyncio.run(expire()).status == BookingStatus.EXPIRED
    response = _confirm(client_db, token, booking, payment_id)
    assert response.status_code == 409
    saved_booking, saved_payment, events = _state(
        workspace_id, booking["id"], payment_id
    )
    assert saved_booking.status == (
        BookingStatus.CANCELLED if ending == "cancel" else BookingStatus.EXPIRED
    )
    assert saved_payment.booking_applied_at is None
    assert all(e.event_type != BookingEventType.BOOKING_CONFIRMED for e in events)
    assert {count for _, count in _inventory_rows(workspace_id)} == {0}


def test_expire_due_batch_skips_booking_confirmed_after_candidate_select(client_db):
    user, token, booking, destination_id, _ = _prepared(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    booking_id = uuid.UUID(booking["id"])
    actor_id = uuid.UUID(user["user"]["id"])
    _advance(client_db, token, booking)
    payment_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]
    _mark_verified(payment_id)

    async def run():
        async with TestSessionLocal() as session:
            service = BookingService(session)
            original_expire = service.expire

            async def confirm_before_expire(ws, identifier, *, now=None):
                async with TestSessionLocal() as confirm_session:
                    await BookingPaymentConfirmationService(confirm_session).confirm(
                        workspace_id, booking_id, uuid.UUID(payment_id), actor_id
                    )
                return await original_expire(ws, identifier, now=now)

            service.expire = confirm_before_expire
            return await service.expire_due_holds(
                workspace_id, now=datetime.now(UTC) + timedelta(minutes=16)
            )

    assert asyncio.run(run()) == 0
    saved_booking, saved_payment, events = _state(
        workspace_id, booking["id"], payment_id
    )
    assert saved_booking.status == BookingStatus.CONFIRMED
    assert saved_payment.booking_applied_at is not None
    assert [e.event_type for e in events].count(BookingEventType.BOOKING_CONFIRMED) == 1
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}
