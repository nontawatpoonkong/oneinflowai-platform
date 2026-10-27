"""Account-scoped provisioning and Workspace-scoped entitlement endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.exceptions import AppError, WorkspaceAccessDeniedError
from app.database.session import get_db
from app.models.billing import (
    PlanEntitlement,
    SaaSPlan,
    SubscriptionWorkspaceAllocation,
    WorkspaceSubscription,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.billing import (
    BillingAccountResponse,
    EntitlementResponse,
    PlanResponse,
    SubscriptionCreateRequest,
    SubscriptionResponse,
    UsageResponse,
)
from app.schemas.response import success_response
from app.services.account_billing import AccountBillingService
from app.services.entitlement import SLIP_VERIFICATIONS, EntitlementService
from app.services.workspace import WorkspaceService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import (
    get_current_workspace,
    require_workspace_capability,
)

router = APIRouter()

# Workspace billing (plan, entitlements, usage, subscription) needs
# workspace.billing.read; owners and admins hold it through the role baseline.
_billing_read = require_workspace_capability(WorkspaceCapability.WORKSPACE_BILLING_READ)
# Payment readers see only the slip-verification quota the Payments page shows.
_PAYMENT_USAGE_KEYS = frozenset({SLIP_VERIFICATIONS})


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


async def _subscription(
    session: AsyncSession,
    service: EntitlementService,
    item: WorkspaceSubscription,
) -> SubscriptionResponse:
    plan = await session.get(SaaSPlan, item.plan_id)
    allocated = await session.scalar(
        select(func.count(SubscriptionWorkspaceAllocation.id)).where(
            SubscriptionWorkspaceAllocation.subscription_id == item.id
        )
    )
    return SubscriptionResponse(
        id=item.id,
        billing_account_id=item.billing_account_id,
        workspace_id=item.workspace_id,
        plan=await _plan(service, plan),
        status=item.status,
        billing_interval=item.billing_interval,
        current_period_start=item.current_period_start,
        current_period_end=item.current_period_end,
        trial_end=item.trial_end,
        cancel_at_period_end=item.cancel_at_period_end,
        provider=item.provider,
        workspace_limit=item.workspace_limit,
        allocated_workspaces=allocated or 0,
    )


async def _may_read_billing(session, workspace_id, user_id) -> bool:
    # Reads the membership directly so a suspended Workspace still shows its
    # subscription to those allowed to read billing.
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if member is None:
        return False
    capabilities = await WorkspaceCapabilityService(session).effective_for_member(
        member
    )
    return WorkspaceCapability.WORKSPACE_BILLING_READ in capabilities


@router.get("/plans")
async def plans(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = EntitlementService(session)
    data = [await _plan(service, item) for item in await service.list_plans()]
    return success_response([item.model_dump(mode="json") for item in data])


@router.get("/account")
async def billing_account(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    account_service = AccountBillingService(session)
    account = await account_service.get_account(user.id)
    if account is None:
        return success_response(None)
    entitlement_service = EntitlementService(session)
    subscriptions = [
        await _subscription(session, entitlement_service, item)
        for item in await account_service.list_subscriptions(user.id)
    ]
    data = BillingAccountResponse(
        id=account.id,
        owner_user_id=account.owner_user_id,
        status=account.status,
        subscriptions=subscriptions,
    )
    return success_response(data.model_dump(mode="json"))


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    payload: SubscriptionCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    item = await AccountBillingService(session).create_pending_subscription(
        owner_user_id=user.id, plan_id=payload.plan_id
    )
    data = await _subscription(session, EntitlementService(session), item)
    return success_response(
        data.model_dump(mode="json"), message="Subscription awaiting activation"
    )


@router.get("/subscription")
async def subscription(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    account_service = AccountBillingService(session)
    owned = await account_service.list_subscriptions(user.id)
    item = owned[0] if owned else None
    service = EntitlementService(session)
    if item is None:
        workspaces = await WorkspaceService(session).list_for_user(user.id)
        # Another account's Workspace subscription is shown only to members who
        # may read that Workspace's billing.
        if workspaces and await _may_read_billing(session, workspaces[0].id, user.id):
            item = await service.latest_subscription(workspaces[0].id)
    if item is None:
        return success_response(None)
    data = await _subscription(session, service, item)
    return success_response(data.model_dump(mode="json"))


@router.get("/entitlements")
async def entitlements(
    workspace: Workspace = Depends(_billing_read),
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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    _, capabilities = await WorkspaceCapabilityService(session).effective(
        workspace.id, user.id
    )
    if WorkspaceCapability.WORKSPACE_BILLING_READ in capabilities:
        visible_keys = None
    elif WorkspaceCapability.PAYMENT_READ in capabilities:
        visible_keys = _PAYMENT_USAGE_KEYS
    else:
        raise WorkspaceAccessDeniedError(
            "Workspace capability required: "
            f"{WorkspaceCapability.WORKSPACE_BILLING_READ.value}"
        )
    service = EntitlementService(session)
    subscription = await service.latest_subscription(workspace.id)
    if subscription is None:
        return success_response([])
    items: list[PlanEntitlement] = await service.plan_entitlements(subscription.plan_id)
    if visible_keys is not None:
        items = [item for item in items if item.key in visible_keys]
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
