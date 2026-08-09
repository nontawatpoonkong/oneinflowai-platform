"""Email verification OTP API tests."""

import asyncio
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.services.auth as auth_service_module
from app.core.otp import generate_numeric_otp, hash_otp, verify_otp
from app.core.security import hash_password
from app.integrations.email.base import EmailDeliveryError, EmailProvider
from app.integrations.email.development import DevelopmentEmailProvider
from app.integrations.email.templates import build_verification_email
from app.models.user import User
from app.models.verification_challenge import VerificationChallenge
from tests.conftest import FakeEmailProvider, TestSessionLocal

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
VERIFY_URL = "/api/v1/auth/verify-email"
RESEND_URL = "/api/v1/auth/resend-verification"


def test_otp_is_exactly_six_numeric_digits() -> None:
    generated = {generate_numeric_otp() for _ in range(100)}

    assert generated
    assert all(len(otp) == 6 and otp.isascii() and otp.isdigit() for otp in generated)


def test_otp_hash_uses_hmac_sha256_and_constant_time_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-only-secret"
    otp = "012345"
    expected = hmac.new(secret.encode(), otp.encode(), hashlib.sha256).hexdigest()
    compared: list[tuple[str, str]] = []

    def _compare_digest(candidate: str, stored: str) -> bool:
        compared.append((candidate, stored))
        return candidate == stored

    monkeypatch.setattr(hmac, "compare_digest", _compare_digest)

    assert hash_otp(otp=otp, secret=secret) == expected
    assert verify_otp(otp=otp, expected_hash=expected, secret=secret) is True
    assert compared == [(expected, expected)]


def _register(client: TestClient, email: str = "verify@example.com"):
    return client.post(
        REGISTER_URL,
        json={
            "email": email,
            "password": "supersecret123",
            "full_name": "Verify User",
        },
    )


async def _load_state(email: str) -> tuple[User, list[VerificationChallenge]]:
    async with TestSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        result = await session.execute(
            select(VerificationChallenge)
            .where(VerificationChallenge.user_id == user.id)
            .order_by(VerificationChallenge.created_at.asc())
        )
        return user, list(result.scalars().all())


async def _make_expired(email: str) -> None:
    async with TestSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        challenge = await session.scalar(
            select(VerificationChallenge).where(
                VerificationChallenge.user_id == user.id
            )
        )
        assert challenge is not None
        challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


async def _allow_resend(email: str) -> None:
    async with TestSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        challenge = await session.scalar(
            select(VerificationChallenge).where(
                VerificationChallenge.user_id == user.id
            )
        )
        assert challenge is not None
        challenge.resend_available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


def test_registration_creates_unverified_user_hashed_challenge_and_email(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    response = _register(client_db)

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["user"]["email_verified"] is False
    assert data["verification_required"] is True
    assert data["verification_type"] == "EMAIL_OTP"
    assert data["verification_expires_in"] == 300
    assert data["resend_after"] == 60
    assert "token" not in data
    user, challenges = asyncio.run(_load_state("verify@example.com"))
    assert user.email_verified is False
    assert len(challenges) == 1
    assert challenges[0].code_hash != fake_email_provider.latest_otp
    assert len(challenges[0].code_hash) == 64
    assert fake_email_provider.deliveries[0]["recipient"] == "verify@example.com"
    assert fake_email_provider.latest_otp not in response.text


def test_unverified_user_cannot_login(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    _register(client_db)

    response = client_db.post(
        LOGIN_URL,
        json={"email": "verify@example.com", "password": "supersecret123"},
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "EMAIL_NOT_VERIFIED"
    assert error["details"]["next_action"] == "VERIFY_EMAIL"


def test_valid_otp_verifies_user_and_unlocks_login(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    _register(client_db)
    verify_response = client_db.post(
        VERIFY_URL,
        json={"email": "verify@example.com", "otp": fake_email_provider.latest_otp},
    )

    assert verify_response.status_code == 200
    assert verify_response.json()["success"] is True
    user, challenges = asyncio.run(_load_state("verify@example.com"))
    assert user.email_verified is True
    assert user.email_verified_at is not None
    assert challenges[0].used_at is not None

    login = client_db.post(
        LOGIN_URL,
        json={"email": "verify@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 200


def test_invalid_otp_increments_attempts_and_locks_at_maximum(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    _register(client_db)

    for _ in range(5):
        response = client_db.post(
            VERIFY_URL,
            json={"email": "verify@example.com", "otp": "000000"},
        )
        assert response.status_code == 400

    _, challenges = asyncio.run(_load_state("verify@example.com"))
    assert challenges[0].failed_attempts == 5
    locked = client_db.post(
        VERIFY_URL,
        json={"email": "verify@example.com", "otp": fake_email_provider.latest_otp},
    )
    assert locked.status_code == 400


def test_invalid_verification_does_not_reveal_account_existence(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    _register(client_db)

    existing = client_db.post(
        VERIFY_URL,
        json={"email": "verify@example.com", "otp": "000000"},
    )
    unknown = client_db.post(
        VERIFY_URL,
        json={"email": "missing@example.com", "otp": "000000"},
    )

    assert existing.status_code == unknown.status_code == 400
    assert existing.json() == unknown.json()


def test_expired_and_used_otp_are_rejected(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    _register(client_db)
    asyncio.run(_make_expired("verify@example.com"))
    expired = client_db.post(
        VERIFY_URL,
        json={"email": "verify@example.com", "otp": fake_email_provider.latest_otp},
    )
    assert expired.status_code == 400

    asyncio.run(_allow_resend("verify@example.com"))
    client_db.post(RESEND_URL, json={"email": "verify@example.com"})
    otp = fake_email_provider.latest_otp
    assert client_db.post(
        VERIFY_URL, json={"email": "verify@example.com", "otp": otp}
    ).status_code == 200
    replay = client_db.post(
        VERIFY_URL, json={"email": "verify@example.com", "otp": otp}
    )
    assert replay.status_code == 400


def test_resend_cooldown_is_generic_and_later_resend_invalidates_old_code(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    _register(client_db)
    first_otp = fake_email_provider.latest_otp

    cooldown = client_db.post(RESEND_URL, json={"email": "verify@example.com"})
    unknown = client_db.post(RESEND_URL, json={"email": "missing@example.com"})
    assert cooldown.status_code == 200
    assert cooldown.json() == unknown.json()
    assert len(fake_email_provider.deliveries) == 1

    asyncio.run(_allow_resend("verify@example.com"))
    resent = client_db.post(RESEND_URL, json={"email": "verify@example.com"})
    assert resent.status_code == 200
    assert len(fake_email_provider.deliveries) == 2
    _, challenges = asyncio.run(_load_state("verify@example.com"))
    assert len(challenges) == 2
    assert challenges[0].used_at is not None
    assert client_db.post(
        VERIFY_URL, json={"email": "verify@example.com", "otp": first_otp}
    ).status_code == 400


def test_unknown_resend_uses_generic_success_response(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    response = client_db.post(RESEND_URL, json={"email": "missing@example.com"})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["resend_after"] == 60
    assert response.json()["message"] == (
        "If an account exists for this email, a verification code has been sent."
    )
    assert not fake_email_provider.deliveries


def test_verified_account_resend_matches_unknown_account_response(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    _register(client_db)
    client_db.post(
        VERIFY_URL,
        json={"email": "verify@example.com", "otp": fake_email_provider.latest_otp},
    )

    verified = client_db.post(RESEND_URL, json={"email": "verify@example.com"})
    unknown = client_db.post(RESEND_URL, json={"email": "missing@example.com"})

    assert verified.status_code == unknown.status_code == 200
    assert verified.json() == unknown.json()


def test_registration_survives_provider_delivery_failure(
    client_db: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingProvider(EmailProvider):
        async def send_verification_otp(self, **kwargs) -> None:
            raise EmailDeliveryError("delivery unavailable")

    monkeypatch.setattr(
        auth_service_module, "create_email_provider", lambda: FailingProvider()
    )
    response = _register(client_db)

    assert response.status_code == 201
    user, challenges = asyncio.run(_load_state("verify@example.com"))
    assert user.email_verified is False
    assert len(challenges) == 1


def test_development_provider_and_template_do_not_log_otp(
    caplog: pytest.LogCaptureFixture,
) -> None:
    otp = "123456"
    content = build_verification_email(otp=otp, expires_in_seconds=300)
    assert "OneInFlow" in content.subject
    assert otp in content.text
    assert "5" in content.text

    asyncio.run(
        DevelopmentEmailProvider().send_verification_otp(
            recipient="user@example.com",
            otp=otp,
            expires_in_seconds=300,
        )
    )
    assert otp not in caplog.text
    assert "user@example.com" not in caplog.text


def test_existing_verified_user_can_login(client_db: TestClient) -> None:
    async def _seed() -> None:
        async with TestSessionLocal() as session:
            session.add(
                User(
                    email="existing@example.com",
                    hashed_password=hash_password("supersecret123"),
                    full_name="Existing User",
                    email_verified=True,
                    email_verified_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(_seed())
    response = client_db.post(
        LOGIN_URL,
        json={"email": "existing@example.com", "password": "supersecret123"},
    )
    assert response.status_code == 200
