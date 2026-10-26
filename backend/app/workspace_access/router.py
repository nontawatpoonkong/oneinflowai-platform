"""Account-level join-code resolution and access-request routes."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.exceptions import (
    DemoRateLimitExceededError,
    DemoRateLimitUnavailableError,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.response import success_response
from app.schemas.workspace_access import (
    AccessRequestCreate,
    AccessRequestResponse,
    JoinCodeResolveRequest,
    JoinCodeWorkspaceResponse,
)
from app.services.public_rate_limit import PublicRateLimitService
from app.services.workspace_access import WorkspaceAccessService

router = APIRouter()


async def _rate_limit(request: Request, user: User) -> None:
    identity = f"{user.id}:{request.client.host if request.client else 'unknown'}"
    try:
        result = await PublicRateLimitService(
            request.app.state.redis, requests=10, window_seconds=60
        ).check("workspace-join", identity)
    except (RedisError, OSError, TimeoutError):
        raise DemoRateLimitUnavailableError(
            "Workspace join lookup is temporarily unavailable"
        ) from None
    if not result.allowed:
        raise DemoRateLimitExceededError(result.retry_after_seconds)


def _request_data(item, *, workspace_name=None, user=None):
    return AccessRequestResponse(
        id=item.id,
        workspace_id=item.workspace_id,
        workspace_name=workspace_name,
        user_id=item.user_id,
        email=user.email if user else None,
        full_name=user.full_name if user else None,
        status=item.status,
        message=item.message,
        requested_at=item.requested_at,
        reviewed_at=item.reviewed_at,
        reviewed_by_user_id=item.reviewed_by_user_id,
        rejection_reason=item.rejection_reason,
    ).model_dump(mode="json")


@router.post("/resolve-code")
async def resolve_code(
    payload: JoinCodeResolveRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _rate_limit(request, user)
    workspace = await WorkspaceAccessService(session).resolve_code(payload.code)
    return success_response(
        JoinCodeWorkspaceResponse(name=workspace.name).model_dump(mode="json")
    )


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def request_access(
    payload: AccessRequestCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _rate_limit(request, user)
    item, created = await WorkspaceAccessService(session).request_access(
        user.id, payload.code, payload.message
    )
    return success_response(
        _request_data(item),
        "Workspace access requested" if created else "Request already pending",
    )


@router.get("/my-requests")
async def my_requests(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    rows = await WorkspaceAccessService(session).my_requests(user.id)
    return success_response(
        [_request_data(item, workspace_name=name) for item, name in rows]
    )


@router.post("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    item = await WorkspaceAccessService(session).cancel_request(user.id, request_id)
    return success_response(_request_data(item), "Access request cancelled")
