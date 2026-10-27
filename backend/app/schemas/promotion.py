"""Typed promotion administration, validation, and reporting contracts."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.promotion import (
    PromotionCampaignStatus,
    PromotionCodeStatus,
    PromotionDiscountType,
    PromotionRedemptionStatus,
    PromotionSource,
)


class PromotionCampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def valid_window(self):
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        return self


class PromotionCampaignUpdate(PromotionCampaignCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def name_not_null(self):
        # Omitting name keeps it; an explicit null would violate NOT NULL.
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class PromotionCampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    status: PromotionCampaignStatus
    valid_from: datetime | None
    valid_until: datetime | None
    created_by_user_id: uuid.UUID | None
    management_origin: str = "WORKSPACE"
    started_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PromotionCreate(BaseModel):
    campaign_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    discount_type: PromotionDiscountType
    discount_value: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    max_discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    minimum_subtotal: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    stay_date_start: date | None = None
    stay_date_end: date | None = None
    total_usage_limit: int | None = Field(default=None, gt=0)
    per_customer_limit: int | None = Field(default=None, gt=0)
    property_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    room_type_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    rate_plan_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    sources: list[PromotionSource] = Field(default_factory=list, max_length=16)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value):
        return value.upper() if value else None

    @model_validator(mode="after")
    def valid_rule(self):
        if self.discount_type is PromotionDiscountType.PERCENTAGE:
            if self.discount_value > Decimal("100"):
                raise ValueError("percentage discount cannot exceed 100")
        elif not self.currency:
            raise ValueError("fixed amount promotion requires currency")
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if (
            self.stay_date_start
            and self.stay_date_end
            and self.stay_date_end < self.stay_date_start
        ):
            raise ValueError("stay_date_end must not precede stay_date_start")
        return self


class PromotionUpdate(PromotionCreate):
    campaign_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    discount_type: PromotionDiscountType | None = None
    discount_value: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )

    @model_validator(mode="after")
    def valid_rule(self):
        if (
            self.discount_type is PromotionDiscountType.PERCENTAGE
            and self.discount_value is not None
            and self.discount_value > Decimal("100")
        ):
            raise ValueError("percentage discount cannot exceed 100")
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        if (
            self.stay_date_start
            and self.stay_date_end
            and self.stay_date_end < self.stay_date_start
        ):
            raise ValueError("stay_date_end must not precede stay_date_start")
        return self


class PromotionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    campaign_id: uuid.UUID
    name: str
    discount_type: PromotionDiscountType
    discount_value: Decimal
    max_discount_amount: Decimal | None
    minimum_subtotal: Decimal | None
    currency: str | None
    valid_from: datetime | None
    valid_until: datetime | None
    stay_date_start: date | None
    stay_date_end: date | None
    total_usage_limit: int | None
    per_customer_limit: int | None
    active: bool
    property_ids: list[uuid.UUID] = Field(default_factory=list)
    room_type_ids: list[uuid.UUID] = Field(default_factory=list)
    rate_plan_ids: list[uuid.UUID] = Field(default_factory=list)
    sources: list[PromotionSource] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PromotionCodeCreate(BaseModel):
    promotion_id: uuid.UUID
    code: str = Field(min_length=1, max_length=32)
    usage_limit: int | None = Field(default=None, gt=0)


class PromotionCodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    promotion_id: uuid.UUID
    code: str
    status: PromotionCodeStatus
    usage_limit: int | None
    created_at: datetime
    updated_at: datetime


class PromotionValidationRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    property_id: uuid.UUID
    room_type_id: uuid.UUID
    rate_plan_id: uuid.UUID
    check_in: date
    check_out: date
    subtotal: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    customer_id: uuid.UUID | None = None
    source: PromotionSource

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value):
        return value.upper()

    @model_validator(mode="after")
    def valid_stay(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class PromotionValidationResult(BaseModel):
    valid: bool
    reason_code: str | None
    promotion_id: uuid.UUID | None
    promotion_code_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    code: str | None
    promotion_name: str | None
    discount_type: PromotionDiscountType | None
    discount_value: Decimal | None
    discount_amount: Decimal
    subtotal: Decimal
    final_total: Decimal
    currency: str


class PromotionRedemptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    promotion_id: uuid.UUID
    promotion_code_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    booking_id: uuid.UUID
    discount_amount: Decimal
    currency: str
    status: PromotionRedemptionStatus
    reserved_until: datetime | None
    redeemed_at: datetime | None
    created_at: datetime
