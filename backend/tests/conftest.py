"""Shared pytest fixtures.

`client`     : external deps faked, DB NOT overridden (used by health tests).
`client_db`  : external deps faked + get_db pointed at a real test Postgres,
               with the schema recreated per test for isolation.
"""

import asyncio
import os
from collections.abc import AsyncGenerator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import app.core.lifespan as lifespan_module
import app.models  # noqa: F401  (register all tables on Base.metadata)
from app.database.base import Base
from app.database.session import get_db
from app.main import app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://oneflowai:oneflowai@127.0.0.1:5432/oneflowai_test",
)

# NullPool => every connection is opened/closed within the current event loop,
# avoiding cross-loop reuse between successive TestClient contexts.
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


class _FakeRedis:
    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class _FakeQdrant:
    async def get_collections(self):
        return []

    async def close(self) -> None:
        return None


def _fake_external_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifespan_module, "create_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(lifespan_module, "create_qdrant_client", lambda: _FakeQdrant())


async def _recreate_schema() -> None:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _fake_external_deps(monkeypatch)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
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
