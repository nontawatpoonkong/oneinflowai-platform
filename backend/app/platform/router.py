"""Dedicated API namespace for trusted OneInFlowAI platform operators."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.session import get_db
from app.models.billing import SubscriptionStatus
from app.models.promotion import (
    PromotionCampaignStatus,
    PromotionCodeStatus,
    PromotionManagementOrigin,
)
from app.models.user import User
from app.models.workspace import WorkspaceStatus
from app.platform.dependencies import require_platform_admin
from app.schemas.platform import (
    PlatformCampaignCreate,
    PlatformCampaignUpdate,
    PlatformCodeCreate,
    PlatformMutationRequest,
    PlatformRuleCreate,
    PlatformSubscriptionActivationRequest,
)
from app.schemas.response import success_response
from app.services.account_billing import AccountBillingService
from app.services.platform_admin import PlatformAdminService
from app.services.platform_campaign import (
    CatalogTargetKind,
    PlatformCampaignService,
    validate_range,
)
from app.services.promotion_lifecycle import PromotionLifecycleService

router = APIRouter()


def _json(value):
    """Encode money as exact decimal strings, never floats."""

    return jsonable_encoder(value, custom_encoder={Decimal: str})


PlatformActor = Annotated[User, Depends(require_platform_admin)]
Database = Annotated[AsyncSession, Depends(get_db)]


@router.get("/overview")
async def overview(actor: PlatformActor, session: Database):
    del actor
    return success_response(await PlatformAdminService(session).overview())


@router.get("/users")
async def list_users(
    actor: PlatformActor,
    session: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, min_length=2, max_length=120),
    verified: bool | None = None,
    active: bool | None = None,
    has_workspace: bool | None = None,
    has_subscription: bool | None = None,
    platform_admin: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
):
    del actor
    return success_response(
        await PlatformAdminService(session).users(
            page=page,
            page_size=page_size,
            search=search,
            verified=verified,
            active=active,
            has_workspace=has_workspace,
            has_subscription=has_subscription,
            platform_admin=platform_admin,
            created_from=created_from,
            created_to=created_to,
        )
    )


@router.get("/users/{user_id}")
async def get_user(user_id: uuid.UUID, actor: PlatformActor, session: Database):
    del actor
    return success_response(await PlatformAdminService(session).user_detail(user_id))


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    user = await PlatformAdminService(session).set_user_active(
        actor=actor, user_id=user_id, active=False, reason=payload.reason
    )
    return success_response({"id": user.id, "status": "SUSPENDED"})


@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    user = await PlatformAdminService(session).set_user_active(
        actor=actor, user_id=user_id, active=True, reason=payload.reason
    )
    return success_response({"id": user.id, "status": "ACTIVE"})


@router.get("/workspaces")
async def list_workspaces(
    actor: PlatformActor,
    session: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, min_length=2, max_length=120),
    status: WorkspaceStatus | None = None,
    subscription_status: SubscriptionStatus | None = None,
    pms_connected: bool | None = None,
    recently_active: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
):
    del actor
    return success_response(
        await PlatformAdminService(session).workspaces(
            page=page,
            page_size=page_size,
            search=search,
            status=status.value if status else None,
            subscription_status=subscription_status.value
            if subscription_status
            else None,
            pms_connected=pms_connected,
            recently_active=recently_active,
            created_from=created_from,
            created_to=created_to,
        )
    )


@router.get("/workspaces/{workspace_id}")
async def get_workspace(
    workspace_id: uuid.UUID, actor: PlatformActor, session: Database
):
    del actor
    return success_response(
        await PlatformAdminService(session).workspace_detail(workspace_id)
    )


@router.post("/workspaces/{workspace_id}/suspend")
async def suspend_workspace(
    workspace_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    item = await PlatformAdminService(session).set_workspace_status(
        actor=actor,
        workspace_id=workspace_id,
        status=WorkspaceStatus.SUSPENDED,
        reason=payload.reason,
    )
    return success_response({"id": item.id, "status": item.status})


@router.post("/workspaces/{workspace_id}/reactivate")
async def reactivate_workspace(
    workspace_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    item = await PlatformAdminService(session).set_workspace_status(
        actor=actor,
        workspace_id=workspace_id,
        status=WorkspaceStatus.ACTIVE,
        reason=payload.reason,
    )
    return success_response({"id": item.id, "status": item.status})


@router.get("/subscriptions")
async def list_subscriptions(
    actor: PlatformActor,
    session: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: SubscriptionStatus | None = None,
    search: str | None = Query(None, min_length=2, max_length=120),
):
    del actor
    return success_response(
        await PlatformAdminService(session).subscriptions(
            page=page,
            page_size=page_size,
            status=status.value if status else None,
            search=search,
        )
    )


@router.post("/subscriptions/{subscription_id}/activate")
async def activate_subscription(
    subscription_id: uuid.UUID,
    payload: PlatformSubscriptionActivationRequest,
    actor: PlatformActor,
    session: Database,
):
    item = await AccountBillingService(session).activate_subscription(
        actor=actor,
        subscription_id=subscription_id,
        target_status=payload.status,
        reason=payload.reason,
    )
    return success_response({"id": item.id, "status": item.status})


@router.get("/plans")
async def list_plans(
    actor: PlatformActor,
    session: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    del actor
    return success_response(
        await PlatformAdminService(session).plans(page=page, page_size=page_size)
    )


@router.get("/marketing/campaigns")
async def list_campaigns(
    actor: PlatformActor,
    session: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    workspace_id: uuid.UUID | None = None,
    status: PromotionCampaignStatus | None = None,
    origin: PromotionManagementOrigin | None = None,
    search: str | None = Query(None, min_length=2, max_length=120),
):
    del actor
    return success_response(
        _json(
            await PlatformCampaignService(session).list_campaigns(
                page=page,
                page_size=page_size,
                workspace_id=workspace_id,
                status=status,
                origin=origin,
                search=search,
            )
        )
    )


@router.post("/marketing/campaigns", status_code=201)
async def create_campaign(
    payload: PlatformCampaignCreate, actor: PlatformActor, session: Database
):
    service = PlatformCampaignService(session)
    item = await service.create_campaign(actor, payload)
    return success_response(_json(await service.campaign_detail(item.id)))


@router.get("/marketing/campaigns/{campaign_id}")
async def get_campaign(campaign_id: uuid.UUID, actor: PlatformActor, session: Database):
    del actor
    return success_response(
        _json(await PlatformCampaignService(session).campaign_detail(campaign_id))
    )


@router.patch("/marketing/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: PlatformCampaignUpdate,
    actor: PlatformActor,
    session: Database,
):
    service = PlatformCampaignService(session)
    await service.update_campaign(actor, campaign_id, payload)
    return success_response(_json(await service.campaign_detail(campaign_id)))


@router.post("/marketing/campaigns/{campaign_id}/rules", status_code=201)
async def create_campaign_rule(
    campaign_id: uuid.UUID,
    payload: PlatformRuleCreate,
    actor: PlatformActor,
    session: Database,
):
    service = PlatformCampaignService(session)
    await service.create_rule(actor, campaign_id, payload)
    return success_response(_json(await service.campaign_detail(campaign_id)))


@router.get("/marketing/campaigns/{campaign_id}/catalog")
async def campaign_catalog(
    campaign_id: uuid.UUID,
    actor: PlatformActor,
    session: Database,
    kind: CatalogTargetKind,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    property_id: uuid.UUID | None = None,
    room_type_id: uuid.UUID | None = None,
    search: str | None = Query(None, min_length=2, max_length=120),
    active_only: bool = True,
):
    return success_response(
        _json(
            await PlatformCampaignService(session).catalog_targets(
                actor,
                campaign_id,
                kind=kind,
                page=page,
                page_size=page_size,
                property_id=property_id,
                room_type_id=room_type_id,
                search=search,
                active_only=active_only,
            )
        )
    )


@router.post("/marketing/campaigns/{campaign_id}/codes", status_code=201)
async def create_campaign_code(
    campaign_id: uuid.UUID,
    payload: PlatformCodeCreate,
    actor: PlatformActor,
    session: Database,
):
    service = PlatformCampaignService(session)
    await service.create_code(actor, campaign_id, payload)
    return success_response(_json(await service.campaign_detail(campaign_id)))


async def _campaign_transition(campaign_id, target, payload, actor, session):
    item = await PlatformCampaignService(session).transition_campaign(
        actor, campaign_id, target, payload.reason
    )
    return success_response({"id": item.id, "status": item.status})


@router.post("/marketing/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    return await _campaign_transition(
        campaign_id, PromotionCampaignStatus.PAUSED, payload, actor, session
    )


@router.post("/marketing/campaigns/{campaign_id}/expire")
async def expire_campaign(
    campaign_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    return await _campaign_transition(
        campaign_id, PromotionCampaignStatus.EXPIRED, payload, actor, session
    )


@router.post("/marketing/campaigns/{campaign_id}/archive")
async def archive_campaign(
    campaign_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    return await _campaign_transition(
        campaign_id, PromotionCampaignStatus.ARCHIVED, payload, actor, session
    )


@router.get("/marketing/codes")
async def list_codes(
    actor: PlatformActor,
    session: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    workspace_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    status: PromotionCodeStatus | None = None,
    search: str | None = Query(None, min_length=1, max_length=32),
):
    del actor
    return success_response(
        _json(
            await PlatformCampaignService(session).list_codes(
                page=page,
                page_size=page_size,
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                status=status,
                search=search,
            )
        )
    )


async def _code_transition(code_id, target, payload, actor, session):
    item = await PlatformCampaignService(session).transition_code(
        actor, code_id, target, payload.reason
    )
    return success_response({"id": item.id, "status": item.status})


@router.post("/marketing/codes/{code_id}/disable")
async def disable_code(
    code_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    return await _code_transition(
        code_id, PromotionCodeStatus.DISABLED, payload, actor, session
    )


@router.post("/marketing/codes/{code_id}/archive")
async def archive_code(
    code_id: uuid.UUID,
    payload: PlatformMutationRequest,
    actor: PlatformActor,
    session: Database,
):
    return await _code_transition(
        code_id, PromotionCodeStatus.ARCHIVED, payload, actor, session
    )


@router.get("/marketing/analytics")
async def marketing_analytics(
    actor: PlatformActor,
    session: Database,
    start: datetime | None = None,
    end: datetime | None = None,
):
    del actor
    start, end = validate_range(start, end)
    return success_response(
        _json(
            await PlatformCampaignService(session).analytics(
                start=start,
                end=end,
                stale_after_seconds=get_settings().PROMOTION_LIFECYCLE_STALE_SECONDS,
            )
        )
    )


@router.get("/marketing/lifecycle")
async def marketing_lifecycle(actor: PlatformActor, session: Database):
    del actor
    return success_response(
        _json(
            await PromotionLifecycleService(session).status(
                stale_after_seconds=get_settings().PROMOTION_LIFECYCLE_STALE_SECONDS
            )
        )
    )


@router.get("/marketing/attribution")
async def marketing_attribution(
    actor: PlatformActor,
    session: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    del actor
    return success_response(
        _json(
            await PlatformAdminService(session).attribution(
                page=page, page_size=page_size
            )
        )
    )


@router.get("/analytics")
async def analytics(actor: PlatformActor, session: Database):
    del actor
    return success_response(_json(await PlatformAdminService(session).analytics()))


@router.get("/operations")
async def operations(actor: PlatformActor, session: Database):
    del actor
    return success_response(await PlatformAdminService(session).operations())


@router.get("/audit/events")
async def audit_events(
    actor: PlatformActor,
    session: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    workspace_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_type: str | None = Query(None, max_length=24),
    area: str | None = Query(None, max_length=32),
    action: str | None = Query(None, max_length=96),
    result: str | None = Query(None, max_length=16),
    resource_type: str | None = Query(None, max_length=64),
    start_at: datetime | None = None,
    end_at: datetime | None = None,
):
    del actor
    return success_response(
        await PlatformAdminService(session).global_audit(
            page=page,
            page_size=page_size,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            area=area,
            action=action,
            result=result,
            resource_type=resource_type,
            start_at=start_at,
            end_at=end_at,
        )
    )


@router.get("/system/health")
async def system_health(actor: PlatformActor, session: Database):
    del actor
    return success_response(await PlatformAdminService(session).system_health())
