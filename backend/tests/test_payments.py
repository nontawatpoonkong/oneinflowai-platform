"""Customer payment creation, action linkage, and evidence security tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.payment as payment_module
from app.core.config import Settings
from app.storage.local import LocalStorageProvider
from tests.conftest import register_verify_and_login
from tests.test_actions import _create as create_action
from tests.test_actions import _definition as create_definition

URL = "/api/v1/payments"
JPEG = b"\xff\xd8\xff" + b"safe-jpeg-fixture"
PNG = b"\x89PNG\r\n\x1a\n" + b"safe-png-fixture"


def _auth(client, email):
    _, token = register_verify_and_login(client, email=email)
    return {"Authorization": f"Bearer {token}"}


def _destination(client, headers, active=True):
    return client.post(
        f"{URL}/destinations",
        headers=headers,
        json={
            "type": "BANK_ACCOUNT",
            "display_name": "Bank",
            "account_number_masked": "xxxx1234",
            "is_active": active,
        },
    ).json()["data"]["id"]


def _payment(client, headers, destination, **extra):
    payload = {
        "payment_destination_id": destination,
        "expected_amount": "1234.50",
        "currency": "THB",
    }
    payload.update(extra)
    return client.post(URL, headers=headers, json=payload)


@pytest.fixture(autouse=True)
def payment_storage(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        payment_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    return tmp_path


def test_decimal_payment_creation_defaults_and_client_fields_ignored(
    client_db: TestClient,
) -> None:
    headers = _auth(client_db, "payment-create@example.com")
    response = _payment(
        client_db,
        headers,
        _destination(client_db, headers),
        workspace_id="00000000-0000-0000-0000-000000000000",
        status="VERIFIED",
        verified_amount="999",
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["expected_amount"] == "1234.50" and data["status"] == "PENDING"
    assert data["verified_amount"] is None


def test_inactive_destination_and_foreign_action_rejected(
    client_db: TestClient,
) -> None:
    first = _auth(client_db, "payment-first@example.com")
    second = _auth(client_db, "payment-second@example.com")
    assert (
        _payment(client_db, first, _destination(client_db, first, False)).status_code
        == 422
    )
    action = create_action(
        client_db, first, create_definition(client_db, first)
    ).json()["data"]
    assert (
        _payment(
            client_db,
            second,
            _destination(client_db, second),
            action_request_id=action["id"],
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    ("filename", "mime", "data"),
    [("slip.jpg", "image/jpeg", JPEG), ("slip.png", "image/png", PNG)],
)
def test_valid_evidence_accepted_without_storage_key(
    client_db: TestClient, filename, mime, data
) -> None:
    headers = _auth(client_db, f"payment-{filename}@example.com")
    payment_id = _payment(client_db, headers, _destination(client_db, headers)).json()[
        "data"
    ]["id"]
    response = client_db.post(
        f"{URL}/{payment_id}/evidence",
        headers=headers,
        files={"file": (filename, data, mime)},
    )
    assert response.status_code == 201
    assert "storage" not in str(response.json()["data"]).lower()


def test_fake_duplicate_and_oversize_evidence_rejected(
    client_db: TestClient, monkeypatch
) -> None:
    headers = _auth(client_db, "payment-evidence-invalid@example.com")
    payment_id = _payment(client_db, headers, _destination(client_db, headers)).json()[
        "data"
    ]["id"]
    fake = client_db.post(
        f"{URL}/{payment_id}/evidence",
        headers=headers,
        files={"file": ("fake.jpg", b"not-image", "image/jpeg")},
    )
    assert fake.status_code == 422
    valid = client_db.post(
        f"{URL}/{payment_id}/evidence",
        headers=headers,
        files={"file": ("slip.jpg", JPEG, "image/jpeg")},
    )
    assert valid.status_code == 201
    duplicate = client_db.post(
        f"{URL}/{payment_id}/evidence",
        headers=headers,
        files={"file": ("copy.jpg", JPEG, "image/jpeg")},
    )
    assert duplicate.status_code == 409
    monkeypatch.setattr(
        payment_module,
        "get_settings",
        lambda: Settings(_env_file=None, PAYMENT_EVIDENCE_MAX_FILE_SIZE_BYTES=4),
    )
    other_payment = _payment(
        client_db, headers, _destination(client_db, headers)
    ).json()["data"]["id"]
    oversize = client_db.post(
        f"{URL}/{other_payment}/evidence",
        headers=headers,
        files={"file": ("large.jpg", b"\xff\xd8\xffxx", "image/jpeg")},
    )
    assert oversize.status_code == 413
