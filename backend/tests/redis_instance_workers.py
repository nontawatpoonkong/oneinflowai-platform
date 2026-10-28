"""Entry points for spawned processes that stand in for application instances.

Each process opens its own Redis connection, waits at a shared barrier, and
then runs the production lease script or rate limiter once per attempt, so
the instances contend for the same keys at the same moment.
"""

import asyncio
import os
import time

from redis.asyncio import Redis

from app.knowledge.upload_limits import _ACQUIRE_LEASE_SCRIPT
from app.services.public_rate_limit import PublicRateLimitService


def acquire_leases(url, barrier, results, lease_key, limit, attempts) -> None:
    async def run() -> list[str]:
        redis = Redis.from_url(url)
        try:
            barrier.wait()
            won = []
            for attempt in range(attempts):
                now = time.time()
                lease_id = f"{os.getpid()}-{attempt}"
                acquired = await redis.eval(
                    _ACQUIRE_LEASE_SCRIPT,
                    1,
                    lease_key,
                    now,
                    now + 60,
                    lease_id,
                    limit,
                    60,
                )
                if int(acquired):
                    won.append(lease_id)
            return won
        finally:
            await redis.aclose()

    results.extend(asyncio.run(run()))


def count_allowed(url, barrier, results, namespace, identity, allowance, attempts):
    async def run() -> int:
        redis = Redis.from_url(url)
        try:
            limiter = PublicRateLimitService(
                redis, requests=allowance, window_seconds=60
            )
            barrier.wait()
            allowed = 0
            for _ in range(attempts):
                if (await limiter.check(namespace, identity)).allowed:
                    allowed += 1
            return allowed
        finally:
            await redis.aclose()

    results.append(asyncio.run(run()))
