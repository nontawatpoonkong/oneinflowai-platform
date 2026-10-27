"""Bounded contracts for the internal Platform Administration Console."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.billing import SubscriptionStatus
from app.schemas.promotion import (
    PromotionCampaignCreate,
    PromotionCampaignUpdate,
    PromotionCodeCreate,
    PromotionCreate,
)


class PlatformMutationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    confirmed: bool

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A meaningful reason is required")
        return value

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Explicit confirmation is required")
        return value


class PlatformSubscriptionActivationRequest(PlatformMutationRequest):
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE


class PlatformListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


class PlatformPage(BaseModel):
    items: list[dict]
    page: int
    page_size: int
    total: int
    total_pages: int


class PlatformHealthResponse(BaseModel):
    database: str
    automation_workers: dict
    queue: dict
    generated_at: datetime
    secrets_exposed: bool = False


class PlatformResourceId(BaseModel):
    id: uuid.UUID


class _Confirmed(BaseModel):
    """Reason + explicit confirmation shared by every platform mutation."""

    reason: str = Field(min_length=3, max_length=500)
    confirmed: bool

    normalize_reason = field_validator("reason")(
        PlatformMutationRequest.normalize_reason.__func__
    )
    require_confirmation = field_validator("confirmed")(
        PlatformMutationRequest.require_confirmation.__func__
    )


class PlatformCampaignCreate(PromotionCampaignCreate, _Confirmed):
    """A platform-managed DRAFT campaign owned (and funded) by one Workspace."""

    workspace_id: uuid.UUID


class PlatformCampaignUpdate(PromotionCampaignUpdate, _Confirmed):
    pass


class PlatformRuleCreate(PromotionCreate, _Confirmed):
    # The path parameter is authoritative; a body value is ignored.
    campaign_id: uuid.UUID | None = None


class PlatformCodeCreate(PromotionCodeCreate, _Confirmed):
    pass
