"""Workspace payment destination API tests."""

from fastapi.testclient import TestClient

from tests.conftest import register_verify_and_login

URL = "/api/v1/payments/destinations"


def _auth(client, email):
    _, token = register_verify_and_login(client, email=email)
    return {"Authorization": f"Bearer {token}"}


def test_create_bank_and_promptpay_destinations_with_safe_responses(
    client_db: TestClient,
) -> None:
    headers = _auth(client_db, "payment-destination@example.com")
    bank = client_db.post(
        URL,
        headers=headers,
        json={
            "type": "BANK_ACCOUNT",
            "display_name": "Main bank",
            "bank_name": "Test Bank",
            "account_name": "Business",
            "account_number_masked": "xxx-x-x1234-x",
            "is_default": True,
        },
    )
    assert bank.status_code == 201 and bank.json()["data"]["is_default"]
    promptpay = client_db.post(
        URL,
        headers=headers,
        json={
            "type": "PROMPTPAY",
            "display_name": "PromptPay",
            "promptpay_type": "PHONE",
            "promptpay_identifier": "0812345678",
            "is_default": True,
        },
    )
    data = promptpay.json()["data"]
    assert data["promptpay_identifier_last4"] == "5678"
    assert "0812345678" not in str(data)
    listed = client_db.get(URL, headers=headers).json()["data"]
    assert (
        listed[0]["id"] == data["id"]
        and sum(item["is_default"] for item in listed) == 1
    )


def test_destination_workspace_isolation_and_authentication(
    client_db: TestClient,
) -> None:
    first = _auth(client_db, "payment-destination-first@example.com")
    second = _auth(client_db, "payment-destination-second@example.com")
    destination = client_db.post(
        URL,
        headers=first,
        json={
            "type": "BANK_ACCOUNT",
            "display_name": "Bank",
            "account_number_masked": "xxxx1234",
        },
    ).json()["data"]
    assert client_db.get(URL).status_code == 401
    assert (
        client_db.patch(
            f"{URL}/{destination['id']}", headers=second, json={"is_active": False}
        ).status_code
        == 404
    )
