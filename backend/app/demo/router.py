"""Public demo chat endpoint; deliberately has no database dependency."""

from fastapi import APIRouter, Depends, Request
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.exceptions import (
    DemoRateLimitExceededError,
    DemoRateLimitUnavailableError,
)
from app.core.logging import get_logger
from app.integrations.generation import create_generation_provider
from app.schemas.demo import DemoChatRequest, DemoChatResponse
from app.schemas.response import success_response
from app.services.demo_chat import DemoChatService
from app.services.public_rate_limit import PublicRateLimitService

router = APIRouter()
logger = get_logger(__name__)


def get_demo_chat_service() -> DemoChatService:
    return DemoChatService(create_generation_provider())


async def enforce_demo_rate_limit(request: Request) -> None:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    limiter = PublicRateLimitService(
        request.app.state.redis,
        requests=settings.DEMO_CHAT_RATE_LIMIT_REQUESTS,
        window_seconds=settings.DEMO_CHAT_RATE_LIMIT_WINDOW_SECONDS,
    )
    try:
        result = await limiter.check("demo-chat", client_host)
    except (RedisError, OSError, TimeoutError):
        logger.warning("demo.rate_limit.unavailable")
        raise DemoRateLimitUnavailableError() from None
    if not result.allowed:
        logger.info(
            "demo.rate_limit.exceeded",
            extra={"client_identity_hash": result.identity_hash},
        )
        raise DemoRateLimitExceededError(result.retry_after_seconds)


@router.post("/chat", dependencies=[Depends(enforce_demo_rate_limit)])
async def chat(
    payload: DemoChatRequest,
    service: DemoChatService = Depends(get_demo_chat_service),
) -> dict:
    result: DemoChatResponse = await service.answer(payload)
    return success_response(result.model_dump(), "Demo answer generated")
