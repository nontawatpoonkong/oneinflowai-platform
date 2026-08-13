"""Application lifespan.

Initializes shared clients (Redis, Qdrant) on startup and disposes all
connection pools (DB, Redis, Qdrant) on shutdown. Clients are stored on
`app.state` so routers/services can reach them via the request object.

Startup does NOT hard-fail if a dependency is unreachable; connectivity is
surfaced by the readiness health check instead. This keeps the container
booting even when a dependency is briefly unavailable.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings, validate_production_settings
from app.core.logging import get_logger
from app.database.qdrant import create_qdrant_client
from app.database.redis import create_redis_client
from app.database.session import engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application.startup.begin")
    validate_production_settings(get_settings())

    app.state.redis = create_redis_client()
    app.state.qdrant = create_qdrant_client()

    logger.info("application.startup.complete")
    try:
        yield
    finally:
        logger.info("application.shutdown.begin")
        try:
            await app.state.redis.aclose()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            logger.warning("application.shutdown.redis_close_failed", exc_info=True)
        try:
            await app.state.qdrant.close()
        except Exception:  # noqa: BLE001
            logger.warning("application.shutdown.qdrant_close_failed", exc_info=True)
        await engine.dispose()
        logger.info("application.shutdown.complete")
