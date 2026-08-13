"""Redis-backed, fail-closed public WebChat rate limit."""

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


async def enforce_webchat_rate_limit(request: Request) -> None:
    settings = get_settings()
    limiter = PublicRateLimitService(
        request.app.state.redis,
        requests=settings.WEBCHAT_RATE_LIMIT_REQUESTS,
        window_seconds=settings.WEBCHAT_RATE_LIMIT_WINDOW_SECONDS,
    )
    try:
        result = await limiter.check(
            "webchat", request.client.host if request.client else "unknown"
        )
    except (RedisError, OSError, TimeoutError):
        logger.warning("webchat.rate_limit.unavailable")
        raise DemoRateLimitUnavailableError() from None
    if not result.allowed:
        raise DemoRateLimitExceededError(result.retry_after_seconds)
