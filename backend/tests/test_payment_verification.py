"""Provider-neutral slip verification and payment integrity tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.payment.router as payment_router
import app.services.payment as payment_module
from app.integrations.slip_verification import (
    DevelopmentSlipVerificationProvider,
    SlipVerificationRequest,
    SlipVerificationResult,
)
from app.storage.local import LocalStorageProvider
from tests.test_payments import JPEG, URL, _auth, _destination, _payment


@pytest.fixture(autouse=True)
def payment_storage(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        payment_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )


class FixtureProvider:
    name = "fixture"

    def __init__(self, result=None, failure=None):
        self.result = result
        self.failure = failure

    async def verify(self, evidence):
        if self.failure:
            raise self.failure
        return self.result


def _result(**overrides):
    values = {
        "provider": "fixture",
        "provider_reference": "provider-ref",
        "is_valid": True,
        "amount": Decimal("1234.50"),
        "currency": "THB",
        "transfer_reference": "transfer-ref",
        "transferred_at": datetime.now(UTC),
        "receiver_match": True,
    }
    values.update(overrides)
    return SlipVerificationResult(**values)


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr(
        payment_router, "create_slip_verification_provider", lambda: provider
    )


@pytest.mark.asyncio
async def test_development_provider_is_deterministic_without_network() -> None:
    request = SlipVerificationRequest("a" * 64, Decimal("100.00"), "THB", "destination")
    provider = DevelopmentSlipVerificationProvider()
    first = await provider.verify(request)
    second = await provider.verify(request)
    assert first == second and first.is_valid and first.amount == Decimal("100.00")


def _submit_and_verify(client, headers, payment_id, data=JPEG):
    submitted = client.post(
        f"{URL}/{payment_id}/evidence",
        headers=headers,
        files={"file": ("slip.jpg", data, "image/jpeg")},
    )
    assert submitted.status_code == 201
    return client.post(f"{URL}/{payment_id}/verify", headers=headers)


def test_valid_exact_payment_verifies_without_completing_action(
    client_db: TestClient,
) -> None:
    from tests.test_actions import (
        _create as create_action,
    )
    from tests.test_actions import (
        _definition as create_definition,
    )

    headers = _auth(client_db, "payment-verify@example.com")
    action = create_action(
        client_db, headers, create_definition(client_db, headers)
    ).json()["data"]
    payment_id = _payment(
        client_db,
        headers,
        _destination(client_db, headers),
        action_request_id=action["id"],
    ).json()["data"]["id"]
    response = _submit_and_verify(client_db, headers, payment_id)
    data = response.json()["data"]
    assert data["payment"]["status"] == "VERIFIED"
    assert data["payment"]["verified_amount"] == "1234.50"
    assert data["verification"]["status"] == "VALID"
    notifications = client_db.get("/api/v1/notifications", headers=headers).json()[
        "data"
    ]["items"]
    assert any(item["type"] == "PAYMENT_VERIFIED" for item in notifications)
    assert (
        client_db.get(f"/api/v1/actions/{action['id']}", headers=headers).json()[
            "data"
        ]["status"]
        == "WAITING"
    )


def test_expired_payment_never_verifies(client_db: TestClient) -> None:
    headers = _auth(client_db, "payment-expired@example.com")
    payment_id = _payment(
        client_db,
        headers,
        _destination(client_db, headers),
        expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    ).json()["data"]["id"]
    response = _submit_and_verify(client_db, headers, payment_id)
    assert response.json()["data"]["payment"]["status"] == "EXPIRED"
    assert response.json()["data"]["verification"] is None


@pytest.mark.parametrize(
    "result",
    [
        _result(amount=Decimal("1234.49")),
        _result(receiver_match=False),
        _result(is_valid=False),
    ],
    ids=["amount-mismatch", "receiver-mismatch", "provider-invalid"],
)
def test_verification_rejects_non_authoritative_match(
    client_db: TestClient, monkeypatch, result
) -> None:
    _use_provider(monkeypatch, FixtureProvider(result=result))
    headers = _auth(client_db, "payment-authoritative-match@example.com")
    payment_id = _payment(client_db, headers, _destination(client_db, headers)).json()[
        "data"
    ]["id"]
    response = _submit_and_verify(client_db, headers, payment_id)
    data = response.json()["data"]
    assert data["payment"]["status"] == "REJECTED"
    assert data["verification"]["status"] == "INVALID"


def test_provider_failure_is_safe_and_payment_remains_retryable(
    client_db: TestClient, monkeypatch
) -> None:
    _use_provider(monkeypatch, FixtureProvider(failure=RuntimeError("raw-secret")))
    headers = _auth(client_db, "payment-provider-error@example.com")
    payment_id = _payment(client_db, headers, _destination(client_db, headers)).json()[
        "data"
    ]["id"]
    response = _submit_and_verify(client_db, headers, payment_id)
    assert response.status_code == 502
    assert "raw-secret" not in response.text
    payment = client_db.get(f"{URL}/{payment_id}", headers=headers).json()["data"]
    assert payment["status"] == "PENDING"


def test_duplicate_transfer_reference_is_rejected_without_constraint_failure(
    client_db: TestClient, monkeypatch
) -> None:
    _use_provider(monkeypatch, FixtureProvider(result=_result()))
    headers = _auth(client_db, "payment-duplicate-transfer@example.com")
    destination_id = _destination(client_db, headers)
    first_id = _payment(client_db, headers, destination_id).json()["data"]["id"]
    second_id = _payment(client_db, headers, destination_id).json()["data"]["id"]
    assert _submit_and_verify(client_db, headers, first_id).status_code == 200
    response = _submit_and_verify(client_db, headers, second_id, JPEG + b"-second")
    data = response.json()["data"]
    assert response.status_code == 200
    assert data["payment"]["status"] == "DUPLICATE"
    assert data["verification"]["status"] == "INVALID"
    assert data["verification"]["error_code"] == "DUPLICATE"


def test_verification_workspace_isolated_and_requires_auth(
    client_db: TestClient,
) -> None:
    first = _auth(client_db, "payment-verify-first@example.com")
    second = _auth(client_db, "payment-verify-second@example.com")
    payment_id = _payment(client_db, first, _destination(client_db, first)).json()[
        "data"
    ]["id"]
    assert client_db.post(f"{URL}/{payment_id}/verify").status_code == 401
    assert (
        client_db.post(f"{URL}/{payment_id}/verify", headers=second).status_code == 404
    )
