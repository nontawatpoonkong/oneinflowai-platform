"""Sprint 9.3 production slip verification security and quota tests."""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.payment.router as payment_router
import app.services.payment as payment_module
from app.integrations.slip_verification import (
    EasySlipVerificationProvider,
    SlipVerificationErrorCode,
    SlipVerificationProviderError,
    SlipVerificationRequest,
    SlipVerificationResult,
)
from app.models.billing import EntitlementKind, PlanEntitlement, SaaSUsageRecord
from app.services.entitlement import SLIP_VERIFICATIONS, EntitlementService
from app.storage.local import LocalStorageProvider
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_payments import JPEG, URL, _destination, _payment


@pytest.fixture(autouse=True)
def payment_storage(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        payment_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )


def _request() -> SlipVerificationRequest:
    return SlipVerificationRequest(
        content_hash="a" * 64,
        content=JPEG,
        mime_type="image/jpeg",
        expected_amount=Decimal("1234.50"),
        currency="THB",
        destination_bank_code=None,
        destination_bank_name=None,
        destination_account_name=None,
        destination_account_masked="xxxx1234",
        destination_promptpay_last4=None,
    )


def _success(*, duplicate=False, amount=1234.5, account="xxx-x-x1234"):
    return {
        "success": True,
        "data": {
            "isDuplicate": duplicate,
            "matchedAccount": None,
            "amountInSlip": amount,
            "rawSlip": {
                "transRef": "trusted-transfer-ref",
                "date": "2026-08-12T10:00:00+07:00",
                "amount": {"local": {"amount": amount, "currency": "THB"}},
                "receiver": {
                    "bank": {"id": "014", "short": "SCB"},
                    "account": {
                        "name": {"th": "OneInFlow Shop"},
                        "bank": {"type": "BANKAC", "account": account},
                    },
                },
            },
        },
        "message": "verified",
    }


@pytest.mark.asyncio
async def test_easyslip_success_is_normalized_without_raw_response_leak():
    captured = {}

    def handler(request: httpx.Request):
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = request.content
        return httpx.Response(200, json=_success())

    provider = EasySlipVerificationProvider(
        "secret-api-key", 2, transport=httpx.MockTransport(handler)
    )
    result = await provider.verify(_request())
    assert result.amount == Decimal("1234.5")
    assert result.currency == "THB"
    assert result.transfer_reference == "trusted-transfer-ref"
    assert result.receiver_account_masked == "xxx-x-x1234"
    assert result.duplicate_reference_signal is False
    assert captured["authorization"] == "Bearer secret-api-key"
    assert b"checkDuplicate" in captured["body"]
    assert "rawSlip" not in repr(result)
    assert "secret-api-key" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "payload", "code"),
    [
        (
            401,
            {"error": {"code": "INVALID_API_KEY", "message": "raw-secret"}},
            "AUTHENTICATION_FAILED",
        ),
        (
            403,
            {"error": {"code": "QUOTA_EXCEEDED", "message": "raw-secret"}},
            "RATE_LIMITED",
        ),
        (
            404,
            {"error": {"code": "SLIP_NOT_FOUND", "message": "raw-secret"}},
            "INVALID_EVIDENCE",
        ),
        (
            500,
            {"error": {"code": "API_SERVER_ERROR", "message": "raw-secret"}},
            "PROVIDER_ERROR",
        ),
    ],
)
async def test_easyslip_errors_are_normalized_and_sanitized(status, payload, code):
    provider = EasySlipVerificationProvider(
        "never-leak",
        2,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=payload)
        ),
    )
    with pytest.raises(SlipVerificationProviderError) as caught:
        await provider.verify(_request())
    assert caught.value.code == code
    assert "never-leak" not in str(caught.value)
    assert payload.get("error", {}).get("message", "") not in str(caught.value)


@pytest.mark.asyncio
async def test_easyslip_timeout_is_normalized():
    def timeout(request):
        raise httpx.ReadTimeout("raw timeout", request=request)

    provider = EasySlipVerificationProvider(
        "never-leak", 1, transport=httpx.MockTransport(timeout)
    )
    with pytest.raises(SlipVerificationProviderError) as caught:
        await provider.verify(_request())
    assert caught.value.code == SlipVerificationErrorCode.TIMEOUT
    assert "raw timeout" not in str(caught.value)


@pytest.mark.asyncio
async def test_easyslip_invalid_success_response_is_rejected():
    provider = EasySlipVerificationProvider(
        "never-leak",
        2,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"success": True, "data": {}})
        ),
    )
    with pytest.raises(SlipVerificationProviderError) as caught:
        await provider.verify(_request())
    assert caught.value.code == SlipVerificationErrorCode.PROVIDER_ERROR


class ProductionFixtureProvider:
    name = "easyslip_v2"

    def __init__(self, *, receiver="xxxx1234", duplicate=False):
        self.calls = 0
        self.receiver = receiver
        self.duplicate = duplicate

    async def verify(self, evidence):
        self.calls += 1
        return SlipVerificationResult(
            provider=self.name,
            provider_reference="provider-ref",
            is_valid=True,
            amount=evidence.expected_amount,
            currency=evidence.currency,
            transfer_reference=f"transfer-{evidence.content_hash}",
            transferred_at=datetime.now(UTC),
            receiver_name=None,
            receiver_account_masked=self.receiver,
            receiver_bank=None,
            duplicate_reference_signal=self.duplicate,
        )


def _register(client: TestClient, email: str):
    data, token = register_verify_and_login(client, email=email)
    return data, {"Authorization": f"Bearer {token}"}


async def _configure(workspace_id: str, *, kind, enabled=True, limit=None):
    async with TestSessionLocal() as session:
        subscription = await EntitlementService(session).latest_subscription(
            uuid.UUID(workspace_id)
        )
        entitlement = await session.scalar(
            select(PlanEntitlement).where(
                PlanEntitlement.plan_id == subscription.plan_id,
                PlanEntitlement.key == SLIP_VERIFICATIONS,
            )
        )
        entitlement.enabled = enabled
        entitlement.kind = kind
        entitlement.limit_value = limit
        await session.commit()


async def _usage(workspace_id: str):
    async with TestSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.coalesce(func.sum(SaaSUsageRecord.quantity), 0)).where(
                    SaaSUsageRecord.workspace_id == uuid.UUID(workspace_id),
                    SaaSUsageRecord.meter == SLIP_VERIFICATIONS,
                )
            )
            or 0
        )


def _submit(client, headers, payment_id, data=JPEG):
    return client.post(
        f"{URL}/{payment_id}/evidence",
        headers=headers,
        files={"file": ("slip.jpg", data, "image/jpeg")},
    )


def test_ineligible_workspace_is_denied_before_provider_and_usage(
    client_db, monkeypatch
):
    data, headers = _register(client_db, "slip-denied@example.com")
    provider = ProductionFixtureProvider()
    monkeypatch.setattr(
        payment_router, "create_slip_verification_provider", lambda: provider
    )
    payment_id = _payment(client_db, headers, _destination(client_db, headers)).json()[
        "data"
    ]["id"]
    assert _submit(client_db, headers, payment_id).status_code == 201
    response = client_db.post(f"{URL}/{payment_id}/verify", headers=headers)
    assert response.status_code == 403
    assert provider.calls == 0
    assert asyncio.run(_usage(data["workspace"]["id"])) == 0


@pytest.mark.parametrize("kind", [EntitlementKind.LIMITED, EntitlementKind.UNLIMITED])
def test_eligible_workspace_verifies_and_records_period_usage(
    client_db, monkeypatch, kind
):
    data, headers = _register(client_db, f"slip-{kind.value.lower()}@example.com")
    asyncio.run(
        _configure(
            data["workspace"]["id"],
            kind=kind,
            limit=2 if kind == EntitlementKind.LIMITED else None,
        )
    )
    provider = ProductionFixtureProvider()
    monkeypatch.setattr(
        payment_router, "create_slip_verification_provider", lambda: provider
    )
    payment_id = _payment(client_db, headers, _destination(client_db, headers)).json()[
        "data"
    ]["id"]
    assert _submit(client_db, headers, payment_id).status_code == 201
    response = client_db.post(f"{URL}/{payment_id}/verify", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["payment"]["status"] == "VERIFIED"
    assert provider.calls == 1
    assert asyncio.run(_usage(data["workspace"]["id"])) == 1


def test_exhausted_quota_and_foreign_payment_never_call_provider(
    client_db, monkeypatch
):
    first, first_headers = _register(client_db, "slip-quota@example.com")
    _, foreign_headers = _register(client_db, "slip-foreign@example.com")
    asyncio.run(
        _configure(first["workspace"]["id"], kind=EntitlementKind.LIMITED, limit=0)
    )
    provider = ProductionFixtureProvider()
    monkeypatch.setattr(
        payment_router, "create_slip_verification_provider", lambda: provider
    )
    payment_id = _payment(
        client_db, first_headers, _destination(client_db, first_headers)
    ).json()["data"]["id"]
    assert _submit(client_db, first_headers, payment_id).status_code == 201
    assert (
        client_db.post(f"{URL}/{payment_id}/verify", headers=first_headers).status_code
        == 409
    )
    assert (
        client_db.post(
            f"{URL}/{payment_id}/verify", headers=foreign_headers
        ).status_code
        == 404
    )
    assert provider.calls == 0


def test_local_evidence_rejection_does_not_consume_usage(client_db, monkeypatch):
    data, headers = _register(client_db, "slip-local-reject@example.com")
    asyncio.run(
        _configure(data["workspace"]["id"], kind=EntitlementKind.LIMITED, limit=1)
    )
    provider = ProductionFixtureProvider()
    monkeypatch.setattr(
        payment_router, "create_slip_verification_provider", lambda: provider
    )
    payment_id = _payment(client_db, headers, _destination(client_db, headers)).json()[
        "data"
    ]["id"]
    response = client_db.post(
        f"{URL}/{payment_id}/evidence",
        headers=headers,
        files={"file": ("fake.jpg", b"not-jpeg", "image/jpeg")},
    )
    assert response.status_code == 422
    assert provider.calls == 0
    assert asyncio.run(_usage(data["workspace"]["id"])) == 0


def test_provider_duplicate_and_wrong_receiver_cannot_verify(client_db, monkeypatch):
    data, headers = _register(client_db, "slip-provider-signals@example.com")
    asyncio.run(_configure(data["workspace"]["id"], kind=EntitlementKind.UNLIMITED))
    destination = _destination(client_db, headers)
    for suffix, provider in [
        (b"-duplicate", ProductionFixtureProvider(duplicate=True)),
        (b"-receiver", ProductionFixtureProvider(receiver="xxxx9999")),
    ]:
        monkeypatch.setattr(
            payment_router,
            "create_slip_verification_provider",
            lambda provider=provider: provider,
        )
        payment_id = _payment(client_db, headers, destination).json()["data"]["id"]
        assert _submit(client_db, headers, payment_id, JPEG + suffix).status_code == 201
        result = client_db.post(f"{URL}/{payment_id}/verify", headers=headers).json()[
            "data"
        ]
        assert result["payment"]["status"] in {"DUPLICATE", "REJECTED"}
        assert result["payment"]["status"] != "VERIFIED"


def test_concurrent_final_quota_allows_only_one_provider_call(client_db, monkeypatch):
    data, headers = _register(client_db, "slip-concurrent@example.com")
    asyncio.run(
        _configure(data["workspace"]["id"], kind=EntitlementKind.LIMITED, limit=1)
    )
    provider = ProductionFixtureProvider()
    monkeypatch.setattr(
        payment_router, "create_slip_verification_provider", lambda: provider
    )
    destination = _destination(client_db, headers)
    payment_ids = []
    for index in range(2):
        payment_id = _payment(client_db, headers, destination).json()["data"]["id"]
        assert (
            _submit(client_db, headers, payment_id, JPEG + bytes([index])).status_code
            == 201
        )
        payment_ids.append(payment_id)

    def verify(payment_id):
        return client_db.post(f"{URL}/{payment_id}/verify", headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(verify, payment_ids))
    assert sorted(statuses) == [200, 409]
    assert provider.calls == 1
    assert asyncio.run(_usage(data["workspace"]["id"])) == 1


def test_verified_repeat_is_idempotent_and_notification_is_not_duplicated(
    client_db, monkeypatch
):
    data, headers = _register(client_db, "slip-repeat@example.com")
    asyncio.run(_configure(data["workspace"]["id"], kind=EntitlementKind.UNLIMITED))
    provider = ProductionFixtureProvider()
    monkeypatch.setattr(
        payment_router, "create_slip_verification_provider", lambda: provider
    )
    payment_id = _payment(client_db, headers, _destination(client_db, headers)).json()[
        "data"
    ]["id"]
    assert _submit(client_db, headers, payment_id).status_code == 201
    first = client_db.post(f"{URL}/{payment_id}/verify", headers=headers)
    second = client_db.post(f"{URL}/{payment_id}/verify", headers=headers)
    assert first.json()["data"] == second.json()["data"]
    assert provider.calls == 1
    notifications = client_db.get("/api/v1/notifications", headers=headers).json()[
        "data"
    ]["items"]
    assert sum(item["type"] == "PAYMENT_VERIFIED" for item in notifications) == 1
    assert asyncio.run(_usage(data["workspace"]["id"])) == 1
