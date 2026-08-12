"""Authenticated read-only SaaS billing endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.database.session import get_db
from app.models.billing import PlanEntitlement, SaaSPlan
from app.models.workspace import Workspace
from app.schemas.billing import (
    EntitlementResponse,
    PlanResponse,
    SubscriptionResponse,
    UsageResponse,
)
from app.schemas.response import success_response
from app.services.entitlement import EntitlementService
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


async def _plan(service: EntitlementService, plan: SaaSPlan) -> PlanResponse:
    entitlements = await service.plan_entitlements(plan.id)
    return PlanResponse(
        **{
            column: getattr(plan, column)
            for column in (
                "id",
                "key",
                "display_name",
                "is_active",
                "billing_interval",
                "price_minor",
                "currency",
                "pricing_note",
            )
        },
        entitlements=[
            EntitlementResponse.model_validate(item) for item in entitlements
        ],
    )


@router.get("/plans")
async def plans(
    _workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    service = EntitlementService(session)
    data = [await _plan(service, item) for item in await service.list_plans()]
    return success_response([item.model_dump(mode="json") for item in data])


@router.get("/subscription")
async def subscription(
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    service = EntitlementService(session)
    item = await service.latest_subscription(workspace.id)
    if item is None:
        return success_response(None)
    plan = await session.get(SaaSPlan, item.plan_id)
    data = SubscriptionResponse(
        id=item.id,
        workspace_id=item.workspace_id,
        plan=await _plan(service, plan),
        status=item.status,
        billing_interval=item.billing_interval,
        current_period_start=item.current_period_start,
        current_period_end=item.current_period_end,
        trial_end=item.trial_end,
        cancel_at_period_end=item.cancel_at_period_end,
        provider=item.provider,
    )
    return success_response(data.model_dump(mode="json"))


@router.get("/entitlements")
async def entitlements(
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    service = EntitlementService(session)
    subscription = await service.latest_subscription(workspace.id)
    if subscription is None:
        return success_response([])
    items = await service.plan_entitlements(subscription.plan_id)
    return success_response(
        [
            EntitlementResponse.model_validate(item).model_dump(mode="json")
            for item in items
        ]
    )


@router.get("/usage")
async def usage(
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    service = EntitlementService(session)
    subscription = await service.latest_subscription(workspace.id)
    if subscription is None:
        return success_response([])
    items: list[PlanEntitlement] = await service.plan_entitlements(subscription.plan_id)
    data = []
    for item in items:
        if not item.enabled:
            data.append(
                UsageResponse(
                    key=item.key,
                    kind=item.kind,
                    enabled=False,
                    limit=item.limit_value,
                    used=None,
                    remaining=None,
                    overage_allowed=item.overage_allowed,
                )
            )
            continue
        try:
            evaluated = await service.evaluate(workspace.id, item.key)
            data.append(
                UsageResponse(
                    key=evaluated.key,
                    kind=evaluated.kind,
                    enabled=evaluated.enabled,
                    limit=evaluated.limit,
                    used=evaluated.used,
                    remaining=evaluated.remaining,
                    overage_allowed=evaluated.overage_allowed,
                )
            )
        except AppError:
            data.append(
                UsageResponse(
                    key=item.key,
                    kind=item.kind,
                    enabled=item.enabled,
                    limit=item.limit_value,
                    used=None,
                    remaining=None,
                    overage_allowed=item.overage_allowed,
                )
            )
    return success_response([item.model_dump(mode="json") for item in data])
