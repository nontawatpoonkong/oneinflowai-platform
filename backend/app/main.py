"""OneFlowAI Platform - FastAPI application entrypoint."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.lifespan import lifespan
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestIDMiddleware
from app.schemas.response import error_response

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # CORS for local frontend development. Registered before RequestIDMiddleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Correlation ID for every request (also feeds the logging context).
    app.add_middleware(RequestIDMiddleware)

    # Health endpoints live at the root (infra concern, not versioned).
    app.include_router(health_router)
    # Versioned domain API.
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    _register_exception_handlers(app)

    logger.info("application.configured", extra={"env": settings.APP_ENV})
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                message=exc.message, code=exc.code, details=exc.details
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_response(
                message="Validation error",
                code="VALIDATION_ERROR",
                details=jsonable_encoder(exc.errors()),
            ),
        )


app = create_app()
