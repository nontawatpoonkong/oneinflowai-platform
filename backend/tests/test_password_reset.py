"""Password-reset OTP and one-time authorization integration tests."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.auth.router as auth_router_module
from app.core.security import hash_password
from app.integrations.email.base import EmailDeliveryError, EmailProvider
from app.models.password_reset_session import PasswordResetSession
from app.models.user import User
from app.models.verification_challenge import (
    VerificationChallenge,
    VerificationPurpose,
)
from tests.conftest import FakeEmailProvider, TestSessionLocal

FORGOT_URL = "/api/v1/auth/forgot-password"
VERIFY_URL = "/api/v1/auth/verify-password-reset"
RESET_URL = "/api/v1/auth/reset-password"
LOGIN_URL = "/api/v1/auth/login"
EMAIL = "reset@example.com"
OLD_PASSWORD = "old-password-123"
NEW_PASSWORD = "new-password-456"
GENERIC_MESSAGE = (
    "If an eligible account exists for this email, "
    "a password reset code has been sent."
)


async def _seed_user(
    *, email: str = EMAIL, verified: bool = True, active: bool = True
) -> None:
    async with TestSessionLocal() as session:
        session.add(
            User(
                email=email,
                hashed_password=hash_password(OLD_PASSWORD),
                full_name="Reset User",
                email_verified=verified,
                email_verified_at=datetime.now(UTC) if verified else None,
                is_active=active,
            )
        )
        await session.commit()


async def _load_challenges(email: str = EMAIL) -> list[VerificationChallenge]:
    async with TestSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        result = await session.execute(
            select(VerificationChallenge)
            .where(
                VerificationChallenge.user_id == user.id,
                VerificationChallenge.purpose == VerificationPurpose.PASSWORD_RESET,
            )
            .order_by(VerificationChallenge.created_at.asc())
        )
        return list(result.scalars().all())


async def _allow_resend_or_expire(*, expire: bool = False) -> None:
    async with TestSessionLocal() as session:
        challenge = await session.scalar(
            select(VerificationChallenge).where(
                VerificationChallenge.purpose == VerificationPurpose.PASSWORD_RESET
            )
        )
        assert challenge is not None
        if expire:
            challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        else:
            challenge.resend_available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


async def _expire_reset_session(token_hash: str | None = None) -> None:
    async with TestSessionLocal() as session:
        stmt = select(PasswordResetSession)
        if token_hash is not None:
            stmt = stmt.where(PasswordResetSession.token_hash == token_hash)
        reset_session = await session.scalar(stmt)
        assert reset_session is not None
        reset_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


def _forgot(client: TestClient, email: str = EMAIL):
    return client.post(FORGOT_URL, json={"email": email})


def _verify(client: TestClient, otp: str, email: str = EMAIL):
    return client.post(VERIFY_URL, json={"email": email, "otp": otp})


def _reset(client: TestClient, token: str, password: str = NEW_PASSWORD):
    return client.post(
        RESET_URL,
        json={
            "reset_token": token,
            "new_password": password,
            "confirm_password": password,
        },
    )


def test_known_user_creates_hashed_challenge_and_fake_delivery(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    response = _forgot(client_db)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["message"] == GENERIC_MESSAGE
    challenges = asyncio.run(_load_challenges())
    assert len(challenges) == 1
    assert challenges[0].code_hash != fake_email_provider.latest_otp
    assert len(challenges[0].code_hash) == 64
    assert fake_email_provider.deliveries[-1]["purpose"] == "password_reset"
    assert fake_email_provider.latest_otp not in response.text


@pytest.mark.parametrize(
    ("email", "verified", "active"),
    [
        ("missing@example.com", None, None),
        (EMAIL, False, True),
        (EMAIL, True, False),
    ],
)
def test_ineligible_accounts_return_identical_generic_response(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    email: str,
    verified: bool | None,
    active: bool | None,
) -> None:
    if verified is not None and active is not None:
        asyncio.run(_seed_user(verified=verified, active=active))
    response = _forgot(client_db, email)

    assert response.status_code == 200
    assert response.json()["message"] == GENERIC_MESSAGE
    assert not fake_email_provider.deliveries


def test_cooldown_and_provider_failure_are_generic(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_seed_user())
    first = _forgot(client_db)
    cooldown = _forgot(client_db)
    assert first.json() == cooldown.json()
    assert len(fake_email_provider.deliveries) == 1

    class FailingProvider(EmailProvider):
        async def send_verification_otp(self, **kwargs) -> None:
            raise NotImplementedError

        async def send_password_reset_otp(self, **kwargs) -> None:
            raise EmailDeliveryError("provider unavailable")

    asyncio.run(_allow_resend_or_expire())
    monkeypatch.setattr(
        auth_router_module, "create_email_provider", lambda: FailingProvider()
    )
    failed = _forgot(client_db)
    assert failed.status_code == 200
    assert failed.json()["message"] == GENERIC_MESSAGE


def test_valid_otp_creates_hashed_one_time_authorization(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    _forgot(client_db)
    response = _verify(client_db, fake_email_provider.latest_otp)

    assert response.status_code == 200
    token = response.json()["data"]["reset_token"]
    assert token and token != fake_email_provider.latest_otp
    async def _state() -> tuple[VerificationChallenge, PasswordResetSession]:
        async with TestSessionLocal() as session:
            challenge = await session.scalar(select(VerificationChallenge))
            reset_session = await session.scalar(select(PasswordResetSession))
            assert challenge is not None and reset_session is not None
            return challenge, reset_session

    challenge, reset_session = asyncio.run(_state())
    assert challenge.used_at is not None
    assert reset_session.token_hash != token
    assert len(reset_session.token_hash) == 64
    assert token not in response.text.replace(token, "", 1)


def test_wrong_missing_expired_and_used_otp_are_generic(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    _forgot(client_db)
    wrong = _verify(client_db, "000000")
    missing = _verify(client_db, "000000", "missing@example.com")
    assert wrong.status_code == missing.status_code == 400
    assert wrong.json() == missing.json()
    assert asyncio.run(_load_challenges())[0].failed_attempts == 1

    asyncio.run(_allow_resend_or_expire(expire=True))
    expired = _verify(client_db, fake_email_provider.latest_otp)
    assert expired.json() == wrong.json()


def test_max_attempts_and_used_otp_are_rejected(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    _forgot(client_db)
    otp = fake_email_provider.latest_otp
    for _ in range(5):
        assert _verify(client_db, "000000").status_code == 400
    assert _verify(client_db, otp).status_code == 400

    asyncio.run(_allow_resend_or_expire())
    _forgot(client_db)
    otp = fake_email_provider.latest_otp
    assert _verify(client_db, otp).status_code == 200
    assert _verify(client_db, otp).status_code == 400


def test_new_challenge_invalidates_previous_code(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    _forgot(client_db)
    old_otp = fake_email_provider.latest_otp
    asyncio.run(_allow_resend_or_expire())
    _forgot(client_db)

    challenges = asyncio.run(_load_challenges())
    assert len(challenges) == 2
    assert challenges[0].used_at is not None
    assert _verify(client_db, old_otp).status_code == 400
    assert _verify(client_db, fake_email_provider.latest_otp).status_code == 200


def test_valid_token_changes_password_and_is_one_time(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    _forgot(client_db)
    token = _verify(client_db, fake_email_provider.latest_otp).json()["data"][
        "reset_token"
    ]
    response = _reset(client_db, token)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert _reset(client_db, token).status_code == 400
    old_login = client_db.post(
        LOGIN_URL, json={"email": EMAIL, "password": OLD_PASSWORD}
    )
    new_login = client_db.post(
        LOGIN_URL, json={"email": EMAIL, "password": NEW_PASSWORD}
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_expired_and_random_tokens_are_rejected(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    _forgot(client_db)
    token = _verify(client_db, fake_email_provider.latest_otp).json()["data"][
        "reset_token"
    ]
    asyncio.run(_expire_reset_session())
    expired = _reset(client_db, token)
    random = _reset(client_db, "x" * 43)
    assert expired.status_code == random.status_code == 400
    assert expired.json() == random.json()


def test_password_policy_and_confirmation_are_enforced(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    _forgot(client_db)
    token = _verify(client_db, fake_email_provider.latest_otp).json()["data"][
        "reset_token"
    ]
    short = _reset(client_db, token, "short")
    mismatch = client_db.post(
        RESET_URL,
        json={
            "reset_token": token,
            "new_password": NEW_PASSWORD,
            "confirm_password": "different-password",
        },
    )
    assert short.status_code == mismatch.status_code == 422


def test_reset_invalidates_other_active_reset_authorizations(
    client_db: TestClient, fake_email_provider: FakeEmailProvider
) -> None:
    asyncio.run(_seed_user())
    _forgot(client_db)
    first_token = _verify(client_db, fake_email_provider.latest_otp).json()["data"][
        "reset_token"
    ]

    async def _add_second() -> None:
        async with TestSessionLocal() as session:
            existing = await session.scalar(select(PasswordResetSession))
            assert existing is not None
            session.add(
                PasswordResetSession(
                    user_id=existing.user_id,
                    challenge_id=existing.challenge_id,
                    token_hash="f" * 64,
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )
            await session.commit()

    asyncio.run(_add_second())
    assert _reset(client_db, first_token).status_code == 200

    async def _all_used() -> bool:
        async with TestSessionLocal() as session:
            result = await session.scalars(select(PasswordResetSession))
            return all(item.used_at is not None for item in result.all())

    assert asyncio.run(_all_used())
