"""Read-only SaaS billing API responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.billing import BillingInterval, EntitlementKind, SubscriptionStatus


class EntitlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    kind: EntitlementKind
    enabled: bool
    limit_value: int | None
    overage_allowed: bool


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    display_name: str
    is_active: bool
    billing_interval: BillingInterval
    price_minor: int | None
    currency: str | None
    pricing_note: str | None
    entitlements: list[EntitlementResponse]


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    plan: PlanResponse
    status: SubscriptionStatus
    billing_interval: BillingInterval
    current_period_start: datetime
    current_period_end: datetime
    trial_end: datetime | None
    cancel_at_period_end: bool
    provider: str | None


class UsageResponse(BaseModel):
    key: str
    kind: EntitlementKind
    enabled: bool
    limit: int | None
    used: int | None
    remaining: int | None
    overage_allowed: bool
