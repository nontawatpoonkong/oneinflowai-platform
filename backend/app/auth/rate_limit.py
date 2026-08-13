"""Shared fail-closed rate limiting for unauthenticated auth endpoints."""

from fastapi import Request
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.exceptions import (
    DemoRateLimitExceededError,
    DemoRateLimitUnavailableError,
)
from app.core.logging import get_logger
from app.services.public_rate_limit import PublicRateLimitService

logger = get_logger(__name__)


async def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    limiter = PublicRateLimitService(
        request.app.state.redis,
        requests=settings.AUTH_RATE_LIMIT_REQUESTS,
        window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    route = request.url.path.rsplit("/", 1)[-1]
    try:
        result = await limiter.check(
            f"auth:{route}", request.client.host if request.client else "unknown"
        )
    except (RedisError, OSError, TimeoutError):
        logger.warning("auth.rate_limit.unavailable", extra={"route": route})
        raise DemoRateLimitUnavailableError() from None
    if not result.allowed:
        raise DemoRateLimitExceededError(result.retry_after_seconds)
