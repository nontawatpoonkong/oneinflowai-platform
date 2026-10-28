"""Knowledge upload limits against a real Redis shared by several processes.

The rest of the suite uses an in-memory Redis double. These tests run only
when REAL_REDIS_URL points at a disposable Redis (never a shared one): they
start several OS processes, each with its own connection, as independent
application instances would, and check that the limits hold across all of
them. Every key they write carries a random prefix and is deleted afterwards.
"""

import asyncio
import multiprocessing
import os
import time
import uuid

import pytest
from redis.asyncio import Redis

from app.knowledge.upload_limits import _ACQUIRE_LEASE_SCRIPT
from tests import redis_instance_workers

REDIS_URL = os.getenv("REAL_REDIS_URL")
INSTANCES = 4

pytestmark = pytest.mark.skipif(
    not REDIS_URL, reason="set REAL_REDIS_URL to a disposable Redis to run these"
)

_CONTEXT = multiprocessing.get_context("spawn")


def _run_instances(target, *args) -> list:
    with _CONTEXT.Manager() as manager:
        barrier = manager.Barrier(INSTANCES)
        results = manager.list()
        processes = [
            _CONTEXT.Process(target=target, args=(REDIS_URL, barrier, results, *args))
            for _ in range(INSTANCES)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(60)
            assert process.exitcode == 0
        return list(results)


def _redis_call(operation):
    async def run():
        redis = Redis.from_url(REDIS_URL)
        try:
            return await operation(redis)
        finally:
            await redis.aclose()

    return asyncio.run(run())


@pytest.fixture
def prefix():
    value = f"test-{uuid.uuid4().hex}"
    yield value

    async def cleanup(redis):
        keys = [key async for key in redis.scan_iter(match=f"*{value}*")]
        if keys:
            await redis.delete(*keys)

    _redis_call(cleanup)


def test_parse_leases_hold_their_limit_across_instances(prefix):
    lease_key = f"knowledge-parse-leases:{prefix}"
    won = _run_instances(redis_instance_workers.acquire_leases, lease_key, 2, 5)
    assert len(won) == 2
    assert _redis_call(lambda redis: redis.zcard(lease_key)) == 2


def test_expired_leases_free_capacity_for_other_instances(prefix):
    lease_key = f"knowledge-parse-leases:{prefix}"
    past = time.time() - 1
    _redis_call(lambda redis: redis.zadd(lease_key, {"crashed-a": past, "b": past}))
    won = _run_instances(redis_instance_workers.acquire_leases, lease_key, 2, 5)
    assert len(won) == 2
    members = _redis_call(lambda redis: redis.zrange(lease_key, 0, -1))
    assert b"crashed-a" not in members


def test_lease_script_sets_an_expiry_on_the_key(prefix):
    lease_key = f"knowledge-parse-leases:{prefix}"

    async def acquire(redis):
        now = time.time()
        await redis.eval(
            _ACQUIRE_LEASE_SCRIPT, 1, lease_key, now, now + 60, "a", 2, 120
        )
        return await redis.ttl(lease_key)

    assert 0 < _redis_call(acquire) <= 120


def test_user_rate_limit_holds_across_instances(prefix):
    allowed = _run_instances(
        redis_instance_workers.count_allowed,
        f"knowledge-upload:user:{prefix}",
        str(uuid.uuid4()),
        7,
        5,
    )
    assert sum(allowed) == 7
