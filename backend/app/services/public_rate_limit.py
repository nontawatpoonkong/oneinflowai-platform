"""Redis-backed rate limiting for public, cost-bearing endpoints."""

import hashlib
import time
from dataclasses import dataclass

from redis.asyncio import Redis

_FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int
    identity_hash: str


class PublicRateLimitService:
    """Atomic fixed-window limiter shared by every application instance."""

    def __init__(self, redis: Redis, *, requests: int, window_seconds: int) -> None:
        self.redis = redis
        self.requests = requests
        self.window_seconds = window_seconds

    async def check(self, namespace: str, client_host: str) -> RateLimitResult:
        identity_hash = hashlib.sha256(
            client_host.strip().lower().encode("utf-8")
        ).hexdigest()[:32]
        window = int(time.time()) // self.window_seconds
        key = f"public-rate-limit:{namespace}:{identity_hash}:{window}"
        current, ttl = await self.redis.eval(
            _FIXED_WINDOW_SCRIPT,
            1,
            key,
            self.window_seconds,
        )
        retry_after = max(int(ttl), 1)
        return RateLimitResult(
            allowed=int(current) <= self.requests,
            retry_after_seconds=retry_after,
            identity_hash=identity_hash,
        )
