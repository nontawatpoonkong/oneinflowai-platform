"""PostgreSQL-backed operational reconciliation and exception safety tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

import app.payment.router as payment_router
import app.services.payment as payment_module
from app.core.exceptions import PaymentVerificationInProgressError
from app.models.audit import WorkspaceAuditEvent
from app.models.booking import BookingEvent, BookingEventType, BookingStatus
from app.models.payment import (
    Payment,
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentStatus,
)
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.booking import BookingService, BookingTransitionError
from app.services.booking_payment_reconciliation import (
    BookingPaymentReconciliationService,
)
from app.services.payment import PaymentVerificationService
from app.storage.local import LocalStorageProvider
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_booking import _inventory_rows
from tests.test_booking_payment_confirmation import (
    _advance,
    _confirm,
    _link,
    _mark_verified,
    _prepared,
    _state,
)
from tests.test_hotel import _auth
from tests.test_payment_verification import _result
from tests.test_payments import JPEG


def _scenario(client, *, units=1):
    user, token, booking, destination_id, _ = _prepared(client, units=units)
    _advance(client, token, booking)
    payment = _link(client, token, booking, destination_id)
    assert payment.status_code == 201, payment.text
    return user, token, booking, destination_id, payment.json()["data"]["id"]


def _retry(client, token, payment_id):
    return client.post(
        f"/api/v1/hotel/payment-exceptions/{payment_id}/reconcile",
        headers=_auth(token),
    )


def _exceptions(client, token, query=""):
    return client.get(f"/api/v1/hotel/payment-exceptions{query}", headers=_auth(token))


def _event_count(workspace_id, booking_id, event_type):
    async def read():
        async with TestSessionLocal() as session:
            events = list(
                (
                    await session.execute(
                        select(BookingEvent).where(
                            BookingEvent.workspace_id == workspace_id,
                            BookingEvent.booking_id == uuid.UUID(booking_id),
                            BookingEvent.event_type == event_type,
                        )
                    )
                ).scalars()
            )
            return len(events)

    return asyncio.run(read())


def test_verified_after_expiry_requires_review_without_resurrection(client_db):
    user, token, booking, _, payment_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])

    async def expire():
        async with TestSessionLocal() as session:
            await BookingService(session).expire(
                workspace_id,
                uuid.UUID(booking["id"]),
                now=datetime.now(UTC) + timedelta(minutes=16),
            )

    asyncio.run(expire())
    _mark_verified(payment_id)
    first = _retry(client_db, token, payment_id)
    second = _retry(client_db, token, payment_id)
    assert first.status_code == second.status_code == 200
    data = first.json()["data"]
    assert data["payment_status"] == "VERIFIED"
    assert data["application_status"] == "REQUIRES_REVIEW"
    assert data["reason"] == "BOOKING_EXPIRED"
    assert data["booking_status"] == "EXPIRED"
    assert second.json()["data"]["reason"] == "BOOKING_EXPIRED"
    saved_booking, saved_payment, _ = _state(workspace_id, booking["id"], payment_id)
    assert saved_booking.status == BookingStatus.EXPIRED
    assert saved_payment.status == PaymentStatus.VERIFIED
    assert saved_payment.booking_applied_at is None
    assert (
        saved_payment.booking_application_reason
        == PaymentApplicationReason.BOOKING_EXPIRED
    )
    assert {count for _, count in _inventory_rows(workspace_id)} == {0}
    assert (
        _event_count(
            workspace_id, booking["id"], BookingEventType.PAYMENT_REQUIRES_REVIEW
        )
        == 1
    )
    listing = _exceptions(client_db, token, "?reason=BOOKING_EXPIRED")
    assert listing.status_code == 200
    assert [row["payment_id"] for row in listing.json()["data"]] == [payment_id]
    for forbidden in (
        "storage_key",
        "content_hash",
        "provider_response",
        "account_number",
    ):
        assert forbidden not in listing.text

    async def global_audit():
        async with TestSessionLocal() as session:
            return await session.scalar(
                select(WorkspaceAuditEvent).where(
                    WorkspaceAuditEvent.workspace_id == workspace_id,
                    WorkspaceAuditEvent.resource_id == uuid.UUID(payment_id),
                    WorkspaceAuditEvent.action == "PAYMENT_REQUIRES_REVIEW",
                )
            )

    audit = asyncio.run(global_audit())
    assert audit.actor_user_id == uuid.UUID(user["user"]["id"])
    assert "payment_evidence" not in audit.safe_metadata


@pytest.mark.parametrize(
    "case,reason",
    [
        ("expected", "AMOUNT_MISMATCH"),
        ("verified", "AMOUNT_MISMATCH"),
        ("currency", "CURRENCY_MISMATCH"),
        ("cancelled", "BOOKING_CANCELLED"),
    ],
)
def test_verified_unapplied_reasons_are_typed_and_discoverable(client_db, case, reason):
    user, token, booking, _, payment_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _mark_verified(payment_id)

    async def mutate():
        async with TestSessionLocal() as session:
            payment = await session.get(Payment, uuid.UUID(payment_id))
            if case == "expected":
                payment.expected_amount += Decimal("1.00")
            elif case == "verified":
                payment.verified_amount += Decimal("1.00")
            elif case == "currency":
                payment.currency = "USD"
            await session.commit()

    asyncio.run(mutate())
    if case == "cancelled":
        assert (
            client_db.post(
                f"/api/v1/hotel/bookings/{booking['id']}/cancel", headers=_auth(token)
            ).status_code
            == 200
        )
    response = _confirm(client_db, token, booking, payment_id)
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == reason
    saved_booking, saved_payment, _ = _state(workspace_id, booking["id"], payment_id)
    assert saved_booking.status == (
        BookingStatus.CANCELLED
        if case == "cancelled"
        else BookingStatus.PENDING_PAYMENT
    )
    assert saved_payment.status == PaymentStatus.VERIFIED
    assert (
        saved_payment.booking_application_status
        == PaymentApplicationStatus.REQUIRES_REVIEW
    )
    assert saved_payment.booking_application_reason.value == reason
    assert saved_payment.booking_applied_at is None
    assert len(_exceptions(client_db, token, f"?reason={reason}").json()["data"]) == 1


def test_replacement_after_rejection_preserves_history_and_applies_once(client_db):
    user, token, booking, destination_id, first_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _mark_verified(first_id, status=PaymentStatus.REJECTED)
    replacement = _link(client_db, token, booking, destination_id)
    assert replacement.status_code == 201, replacement.text
    second_id = replacement.json()["data"]["id"]
    assert second_id != first_id
    assert (
        _link(client_db, token, booking, destination_id).json()["data"]["id"]
        == second_id
    )
    _mark_verified(second_id)
    applied = _retry(client_db, token, second_id)
    assert applied.status_code == 200
    assert applied.json()["data"]["application_status"] == "APPLIED"
    assert applied.json()["data"]["reason"] is None
    booking_row, second_payment, _ = _state(workspace_id, booking["id"], second_id)
    _, first_payment, _ = _state(workspace_id, booking["id"], first_id)
    assert booking_row.status == BookingStatus.CONFIRMED
    assert second_payment.booking_applied_at is not None
    assert first_payment.status == PaymentStatus.REJECTED
    assert first_payment.booking_applied_at is None
    assert (
        _event_count(
            workspace_id, booking["id"], BookingEventType.REPLACEMENT_PAYMENT_LINKED
        )
        == 1
    )
    assert (
        _event_count(workspace_id, booking["id"], BookingEventType.BOOKING_CONFIRMED)
        == 1
    )
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}


def test_simultaneous_reconciliation_of_same_payment_is_idempotent(client_db):
    user, token, booking, _, payment_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _mark_verified(payment_id)

    async def one():
        async with TestSessionLocal() as session:
            payment, booking_row = await BookingPaymentReconciliationService(
                session
            ).reconcile_payment(workspace_id, uuid.UUID(payment_id))
            return payment.booking_application_status, booking_row.status

    async def run():
        return await asyncio.gather(one(), one())

    assert (
        asyncio.run(run())
        == [(PaymentApplicationStatus.APPLIED, BookingStatus.CONFIRMED)] * 2
    )
    assert (
        _event_count(workspace_id, booking["id"], BookingEventType.BOOKING_CONFIRMED)
        == 1
    )


def test_two_verified_attempts_racing_apply_only_once(client_db):
    user, token, booking, destination_id, first_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _mark_verified(first_id, status=PaymentStatus.REJECTED)
    second_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]
    _mark_verified(first_id)
    _mark_verified(second_id)

    async def one(payment_id):
        async with TestSessionLocal() as session:
            payment, _ = await BookingPaymentReconciliationService(
                session
            ).reconcile_payment(workspace_id, uuid.UUID(payment_id))
            return payment.booking_application_status

    async def run():
        return await asyncio.gather(one(first_id), one(second_id))

    assert set(asyncio.run(run())) == {
        PaymentApplicationStatus.APPLIED,
        PaymentApplicationStatus.REQUIRES_REVIEW,
    }
    first_booking, first_payment, _ = _state(workspace_id, booking["id"], first_id)
    _, second_payment, _ = _state(workspace_id, booking["id"], second_id)
    assert first_booking.status == BookingStatus.CONFIRMED
    assert (
        sum(
            payment.booking_applied_at is not None
            for payment in (first_payment, second_payment)
        )
        == 1
    )
    assert (
        _event_count(workspace_id, booking["id"], BookingEventType.BOOKING_CONFIRMED)
        == 1
    )
    assert {count for _, count in _inventory_rows(workspace_id)} == {1}


def test_expiry_and_reconciliation_race_never_resurrects_booking(client_db):
    user, token, booking, _, payment_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    booking_id = uuid.UUID(booking["id"])
    _mark_verified(payment_id)

    async def reconcile():
        async with TestSessionLocal() as session:
            return await BookingPaymentReconciliationService(session).reconcile_payment(
                workspace_id, uuid.UUID(payment_id)
            )

    async def expire():
        async with TestSessionLocal() as session:
            return await BookingService(session).expire(
                workspace_id,
                booking_id,
                now=datetime.now(UTC) + timedelta(minutes=16),
            )

    async def run():
        return await asyncio.gather(reconcile(), expire(), return_exceptions=True)

    results = asyncio.run(run())
    saved_booking, saved_payment, _ = _state(workspace_id, booking["id"], payment_id)
    assert saved_booking.status in {BookingStatus.CONFIRMED, BookingStatus.EXPIRED}
    if saved_booking.status == BookingStatus.CONFIRMED:
        assert isinstance(results[1], BookingTransitionError)
        assert (
            saved_payment.booking_application_status == PaymentApplicationStatus.APPLIED
        )
        assert {count for _, count in _inventory_rows(workspace_id)} == {1}
    else:
        assert (
            saved_payment.booking_application_status
            == PaymentApplicationStatus.REQUIRES_REVIEW
        )
        assert (
            saved_payment.booking_application_reason
            == PaymentApplicationReason.BOOKING_EXPIRED
        )
        assert {count for _, count in _inventory_rows(workspace_id)} == {0}
    assert (
        _event_count(workspace_id, booking["id"], BookingEventType.BOOKING_CONFIRMED)
        <= 1
    )


def test_member_can_read_exceptions_but_cannot_resolve_them(client_db):
    user, token, booking, _, payment_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _mark_verified(payment_id, amount=Decimal("1.00"))
    assert _retry(client_db, token, payment_id).status_code == 200

    async def demote():
        async with TestSessionLocal() as session:
            await session.execute(
                update(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .values(role=WorkspaceRole.MEMBER)
            )
            await session.commit()

    asyncio.run(demote())
    # F3: membership alone no longer exposes payment exceptions.
    denied = _exceptions(client_db, token)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    async def grant_payment_read():
        async with TestSessionLocal() as session:
            member = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id
                )
            )
            session.add(
                WorkspaceMemberCapability(
                    workspace_id=workspace_id,
                    membership_id=member.id,
                    capability="payment.read",
                    granted_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(grant_payment_read())
    assert _exceptions(client_db, token).status_code == 200
    assert _retry(client_db, token, payment_id).status_code == 403
    assert (
        client_db.post(
            f"/api/v1/hotel/payment-exceptions/{payment_id}/acknowledge",
            headers=_auth(token),
            json={"note": "Investigating"},
        ).status_code
        == 403
    )


def test_acknowledge_review_is_audited_without_financial_mutation(client_db):
    user, token, booking, _, payment_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _mark_verified(payment_id, amount=Decimal("1.00"))
    assert _retry(client_db, token, payment_id).status_code == 200
    url = f"/api/v1/hotel/payment-exceptions/{payment_id}/acknowledge"
    first = client_db.post(url, headers=_auth(token), json={"note": "Contact guest"})
    second = client_db.post(url, headers=_auth(token), json={"note": "Contact guest"})
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["review_note"] == "Contact guest"
    assert (
        _event_count(
            workspace_id, booking["id"], BookingEventType.PAYMENT_REVIEW_ACKNOWLEDGED
        )
        == 1
    )
    saved_booking, saved_payment, _ = _state(workspace_id, booking["id"], payment_id)
    assert saved_booking.status == BookingStatus.PENDING_PAYMENT
    assert saved_payment.status == PaymentStatus.VERIFIED
    assert saved_payment.booking_applied_at is None


def test_exception_listing_is_workspace_scoped(client_db):
    _, token, booking, _, payment_id = _scenario(client_db)
    _mark_verified(payment_id, amount=Decimal("1.00"))
    assert _retry(client_db, token, payment_id).status_code == 200
    _, other_token = register_verify_and_login(
        client_db, email="other-reconciliation@example.com"
    )
    assert _exceptions(client_db, other_token).json()["data"] == []
    assert _retry(client_db, other_token, payment_id).status_code == 404


class _CountingProvider:
    name = "development"

    def __init__(self, result, *, expire=None):
        self.result = result
        self.expire = expire
        self.calls = 0

    async def verify(self, evidence):
        self.calls += 1
        if self.expire:
            workspace_id, booking_id = self.expire
            async with TestSessionLocal() as session:
                await BookingService(session).expire(
                    workspace_id,
                    booking_id,
                    now=datetime.now(UTC) + timedelta(minutes=16),
                )
        return self.result


def test_concurrent_duplicate_verification_claims_payment_once(
    client_db, monkeypatch, tmp_path
):
    user, token, booking, _, payment_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    storage = LocalStorageProvider(tmp_path)
    monkeypatch.setattr(
        payment_module, "create_storage_provider", lambda settings: storage
    )
    evidence = client_db.post(
        f"/api/v1/payments/{payment_id}/evidence",
        headers=_auth(token),
        files={"file": ("slip.jpg", JPEG, "image/jpeg")},
    )
    assert evidence.status_code == 201, evidence.text

    class PausedProvider:
        name = "development"

        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = 0

        async def verify(self, evidence):
            self.calls += 1
            self.entered.set()
            await self.release.wait()
            return _result(
                amount=Decimal(booking["total_amount"]),
                transfer_reference=str(uuid.uuid4()),
            )

    async def run():
        provider = PausedProvider()
        async with (
            TestSessionLocal() as first_session,
            TestSessionLocal() as second_session,
        ):
            first = asyncio.create_task(
                PaymentVerificationService(
                    first_session, provider, storage=storage
                ).verify(workspace_id, uuid.UUID(payment_id))
            )
            await asyncio.wait_for(provider.entered.wait(), 5)
            with pytest.raises(PaymentVerificationInProgressError):
                await PaymentVerificationService(
                    second_session, provider, storage=storage
                ).verify(workspace_id, uuid.UUID(payment_id))
            await second_session.rollback()
            provider.release.set()
            payment, verification = await asyncio.wait_for(first, 5)
            assert payment.status == PaymentStatus.VERIFIED
            assert verification is not None
            assert provider.calls == 1

    asyncio.run(run())
    saved_booking, saved_payment, _ = _state(workspace_id, booking["id"], payment_id)
    assert saved_booking.status == BookingStatus.CONFIRMED
    assert saved_payment.booking_application_status == PaymentApplicationStatus.APPLIED


@pytest.mark.parametrize("late", [False, True])
def test_real_verification_boundary_reconciles_and_replay_is_safe(
    client_db, monkeypatch, tmp_path, late
):
    user, token, booking, _, payment_id = _scenario(client_db)
    workspace_id = uuid.UUID(user["workspace"]["id"])
    provider = _CountingProvider(
        _result(
            amount=Decimal(booking["total_amount"]),
            transfer_reference=str(uuid.uuid4()),
        ),
        expire=(workspace_id, uuid.UUID(booking["id"])) if late else None,
    )
    monkeypatch.setattr(
        payment_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    monkeypatch.setattr(
        payment_router, "create_slip_verification_provider", lambda: provider
    )
    evidence = client_db.post(
        f"/api/v1/payments/{payment_id}/evidence",
        headers=_auth(token),
        files={"file": ("slip.jpg", JPEG, "image/jpeg")},
    )
    assert evidence.status_code == 201, evidence.text
    first = client_db.post(
        f"/api/v1/payments/{payment_id}/verify", headers=_auth(token)
    )
    second = client_db.post(
        f"/api/v1/payments/{payment_id}/verify", headers=_auth(token)
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["payment"]["status"] == "VERIFIED"
    assert provider.calls == 1
    saved_booking, saved_payment, _ = _state(workspace_id, booking["id"], payment_id)
    if late:
        assert saved_booking.status == BookingStatus.EXPIRED
        assert (
            saved_payment.booking_application_status
            == PaymentApplicationStatus.REQUIRES_REVIEW
        )
        assert (
            saved_payment.booking_application_reason
            == PaymentApplicationReason.BOOKING_EXPIRED
        )
        assert saved_payment.booking_applied_at is None
        assert {count for _, count in _inventory_rows(workspace_id)} == {0}
    else:
        assert saved_booking.status == BookingStatus.CONFIRMED
        assert (
            saved_payment.booking_application_status == PaymentApplicationStatus.APPLIED
        )
        assert {count for _, count in _inventory_rows(workspace_id)} == {1}
    assert _event_count(
        workspace_id, booking["id"], BookingEventType.BOOKING_CONFIRMED
    ) == (0 if late else 1)
