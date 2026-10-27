"""Workspace-scoped promotion administration and validation APIs."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.promotion import PromotionCampaignStatus, PromotionCodeStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.promotion import (
    PromotionCampaignCreate,
    PromotionCampaignResponse,
    PromotionCampaignUpdate,
    PromotionCodeCreate,
    PromotionCodeResponse,
    PromotionCreate,
    PromotionRedemptionResponse,
    PromotionResponse,
    PromotionUpdate,
    PromotionValidationRequest,
)
from app.schemas.response import success_response
from app.services.promotion import PromotionService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


async def _require(session, workspace, user, capability):
    await WorkspaceCapabilityService(session).require(workspace.id, user.id, capability)


def _data(schema, value):
    return schema.model_validate(value, from_attributes=True).model_dump(mode="json")


@router.get("/campaigns")
async def list_campaigns(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_READ)
    values = await PromotionService(session).list_campaigns(workspace.id)
    return success_response(
        [_data(PromotionCampaignResponse, value) for value in values]
    )


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: PromotionCampaignCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_MANAGE)
    value = await PromotionService(session).create_campaign(
        workspace.id, user.id, payload
    )
    return success_response(_data(PromotionCampaignResponse, value))


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_READ)
    value = await PromotionService(session).get_campaign(workspace.id, campaign_id)
    return success_response(_data(PromotionCampaignResponse, value))


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: PromotionCampaignUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_MANAGE)
    value = await PromotionService(session).update_campaign(
        workspace.id, user.id, campaign_id, payload
    )
    return success_response(_data(PromotionCampaignResponse, value))


async def _campaign_transition(campaign_id, target, workspace, user, session):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_MANAGE)
    value = await PromotionService(session).transition_campaign(
        workspace.id, user.id, campaign_id, target, idempotent=True
    )
    return success_response(_data(PromotionCampaignResponse, value))


@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _campaign_transition(
        campaign_id, PromotionCampaignStatus.ACTIVE, workspace, user, session
    )


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _campaign_transition(
        campaign_id, PromotionCampaignStatus.PAUSED, workspace, user, session
    )


@router.post("/campaigns/{campaign_id}/archive")
async def archive_campaign(
    campaign_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _campaign_transition(
        campaign_id, PromotionCampaignStatus.ARCHIVED, workspace, user, session
    )


@router.post("/campaigns/{campaign_id}/expire")
async def expire_campaign(
    campaign_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _campaign_transition(
        campaign_id, PromotionCampaignStatus.EXPIRED, workspace, user, session
    )


@router.get("")
async def list_promotions(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_READ)
    values = await PromotionService(session).list_promotions(workspace.id)
    return success_response([_data(PromotionResponse, value) for value in values])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_promotion(
    payload: PromotionCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_MANAGE)
    value = await PromotionService(session).create_promotion(
        workspace.id, user.id, payload
    )
    return success_response(_data(PromotionResponse, value))


@router.patch("/rules/{promotion_id}")
async def update_promotion(
    promotion_id: uuid.UUID,
    payload: PromotionUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_MANAGE)
    value = await PromotionService(session).update_promotion(
        workspace.id, user.id, promotion_id, payload
    )
    return success_response(_data(PromotionResponse, value))


@router.get("/codes")
async def list_codes(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_READ)
    values = await PromotionService(session).list_codes(workspace.id)
    return success_response([_data(PromotionCodeResponse, value) for value in values])


@router.post("/codes", status_code=status.HTTP_201_CREATED)
async def create_code(
    payload: PromotionCodeCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_MANAGE)
    value = await PromotionService(session).create_code(workspace.id, user.id, payload)
    return success_response(_data(PromotionCodeResponse, value))


async def _code_transition(code_id, target, workspace, user, session):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_MANAGE)
    value = await PromotionService(session).transition_code(
        workspace.id, user.id, code_id, target, idempotent=True
    )
    return success_response(_data(PromotionCodeResponse, value))


@router.post("/codes/{code_id}/disable")
async def disable_code(
    code_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _code_transition(
        code_id, PromotionCodeStatus.DISABLED, workspace, user, session
    )


@router.post("/codes/{code_id}/enable")
async def enable_code(
    code_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _code_transition(
        code_id, PromotionCodeStatus.ACTIVE, workspace, user, session
    )


@router.post("/codes/{code_id}/archive")
async def archive_code(
    code_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await _code_transition(
        code_id, PromotionCodeStatus.ARCHIVED, workspace, user, session
    )


@router.post("/validate")
async def validate_code(
    payload: PromotionValidationRequest,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_READ)
    value = await PromotionService(session).validate(workspace.id, payload)
    return success_response(value.model_dump(mode="json"))


@router.get("/redemptions")
async def list_redemptions(
    limit: int = Query(default=100, ge=1, le=200),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _require(session, workspace, user, WorkspaceCapability.PROMOTION_READ)
    values = await PromotionService(session).list_redemptions(workspace.id, limit)
    return success_response(
        [_data(PromotionRedemptionResponse, value) for value in values]
    )
