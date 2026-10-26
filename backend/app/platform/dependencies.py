"""Authorization dependencies dedicated to OneInFlowAI platform operators."""

from typing import Annotated

from fastapi import Depends

from app.auth.dependencies import get_current_user
from app.core.exceptions import PlatformAdminRequiredError
from app.models.user import User


async def require_platform_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_platform_admin:
        raise PlatformAdminRequiredError()
    return user
