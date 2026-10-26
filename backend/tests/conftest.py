"""Shared pytest fixtures.

`client`     : external deps faked, DB NOT overridden (used by health tests).
`client_db`  : external deps faked + get_db pointed at a real test Postgres,
               with the schema recreated per test for isolation.
"""

import asyncio
import base64
import os
import uuid
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Required secret for deterministic OTP hashing in tests only.
os.environ.setdefault("OTP_HASH_SECRET", "test-only-otp-hash-secret")
os.environ.setdefault("EMBEDDING_PROVIDER", "development")
os.environ.setdefault("GENERATION_PROVIDER", "development")
os.environ.setdefault("TRUSTED_HOSTS", "localhost,127.0.0.1,testserver")
os.environ.setdefault("CHANNEL_WEBHOOK_MAX_BYTES", "1000000")
os.environ.setdefault(
    "CHANNEL_CREDENTIAL_ENCRYPTION_KEY",
    base64.b64encode(b"0123456789abcdef0123456789abcdef").decode(),
)

import app.auth.router as auth_router_module
import app.core.lifespan as lifespan_module
import app.models  # noqa: F401  (register all tables on Base.metadata)
import app.services.auth as auth_service_module
from app.database.base import Base
from app.database.session import get_db
from app.integrations.email.base import EmailProvider
from app.main import app
from app.models.billing import (
    BillingInterval,
    SubscriptionStatus,
    WorkspaceSubscription,
)
from app.services.account_billing import AccountBillingService
from app.services.entitlement import EntitlementService

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://oneflowai:oneflowai@localhost:5432/oneflowai_test",
)

# NullPool => every connection is opened/closed within the current event loop,
# avoiding cross-loop reuse between successive TestClient contexts.
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def ping(self) -> bool:
        return True

    async def eval(self, script, key_count, key, window):
        self.values[key] = self.values.get(key, 0) + 1
        return [self.values[key], int(window)]

    async def aclose(self) -> None:
        return None


class _FakeQdrant:
    async def get_collections(self):
        return []

    async def close(self) -> None:
        return None


class FakeEmailProvider(EmailProvider):
    def __init__(self) -> None:
        self.deliveries: list[dict[str, object]] = []

    @property
    def latest_otp(self) -> str:
        return str(self.deliveries[-1]["otp"])

    async def send_verification_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_seconds: int,
    ) -> None:
        self.deliveries.append(
            {
                "recipient": recipient,
                "otp": otp,
                "expires_in_seconds": expires_in_seconds,
            }
        )

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_seconds: int,
    ) -> None:
        self.deliveries.append(
            {
                "recipient": recipient,
                "otp": otp,
                "expires_in_seconds": expires_in_seconds,
                "purpose": "password_reset",
            }
        )


def provision_active_test_subscription(user_id: str) -> str:
    """Create a trusted active Pilot subscription for test setup only."""

    async def provision() -> str:
        async with TestSessionLocal() as session:
            account = await AccountBillingService(session).get_or_create_account(
                uuid.UUID(user_id)
            )
            plan_id = await EntitlementService(session).ensure_reference_catalog()
            now = datetime.now(UTC)
            subscription = WorkspaceSubscription(
                billing_account_id=account.id,
                workspace_id=None,
                plan_id=plan_id,
                status=SubscriptionStatus.ACTIVE,
                billing_interval=BillingInterval.MONTH,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                provider="test_manual_activation",
                workspace_limit=1,
            )
            session.add(subscription)
            await session.commit()
            return str(subscription.id)

    return asyncio.run(provision())

@pytest.fixture
def fake_email_provider(monkeypatch: pytest.MonkeyPatch) -> FakeEmailProvider:
    provider = FakeEmailProvider()
    monkeypatch.setattr(
        auth_service_module, "create_email_provider", lambda: provider
    )
    monkeypatch.setattr(
        auth_router_module, "create_email_provider", lambda: provider
    )
    app.state.fake_email_provider = provider
    return provider


def register_verify_and_login(
    client: TestClient,
    *,
    email: str,
    full_name: str = "Owner",
) -> tuple[dict, str]:
    """Create and verify a user through the public auth flow, then log in."""
    password = "supersecret123"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert registered.status_code == 201
    provider: FakeEmailProvider = client.app.state.fake_email_provider
    verified = client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "otp": provider.latest_otp},
    )
    assert verified.status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    subscription_id = provision_active_test_subscription(
        registered.json()["data"]["user"]["id"]
    )
    workspace = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": email.rsplit("@", 1)[-1].split(".", 1)[0].title(),
            "subscription_id": subscription_id,
        },
    )
    assert workspace.status_code == 201
    data = registered.json()["data"]
    data["workspace"] = workspace.json()["data"]
    return data, token


def _fake_external_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifespan_module, "create_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(lifespan_module, "create_qdrant_client", lambda: _FakeQdrant())


async def _recreate_schema() -> None:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    async with TestSessionLocal() as session:
        await EntitlementService(session).ensure_reference_catalog()
        await session.commit()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _fake_external_deps(monkeypatch)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_db(
    monkeypatch: pytest.MonkeyPatch,
    fake_email_provider: FakeEmailProvider,
) -> Iterator[TestClient]:
    _fake_external_deps(monkeypatch)
    asyncio.run(_recreate_schema())

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
