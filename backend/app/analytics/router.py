"""Authenticated management analytics endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.analytics import AnalyticsOverview
from app.schemas.audit import ProductUsageEventCreate, ProductUsageEventResponse
from app.schemas.response import success_response
from app.services.analytics import AnalyticsService
from app.services.audit import ProductUsageService
from app.services.entitlement import ANALYTICS_BASIC, EntitlementService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def ingest_event(
    data: ProductUsageEventCreate,
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    """Record trusted first-party navigation telemetry.

    Workspace and user identity always come from authenticated context; neither
    can be selected by the submitted payload.
    """

    item = await ProductUsageService(session).ingest(
        workspace_id=workspace.id,
        user_id=user.id,
        data=data,
    )
    return success_response(
        ProductUsageEventResponse.model_validate(item, from_attributes=True).model_dump(
            mode="json"
        )
    )


@router.get("/overview")
async def overview(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=30)
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "Analytics range must include a timezone")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if start >= end or end - start > timedelta(days=366):
        raise HTTPException(422, "Analytics range is invalid")
    await WorkspaceCapabilityService(session).require(
        workspace.id, user.id, WorkspaceCapability.ANALYTICS_READ
    )
    await EntitlementService(session).require(workspace.id, ANALYTICS_BASIC)
    data = await AnalyticsService(session).overview(workspace.id, start, end)
    return success_response(
        AnalyticsOverview.model_validate(data).model_dump(mode="json")
    )
