from app.core.exceptions import AppError


class DevelopmentBillingProvider:
    name = "development"

    async def create_checkout(self, *args, **kwargs) -> str:
        raise AppError("Production billing checkout is not configured")

    async def verify_event(self, payload: bytes, signature: str) -> dict:
        raise AppError("Development billing provider accepts no public events")
