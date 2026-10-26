"""Authoritative, Decimal-safe promotion validation and lifecycle service."""

import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.audit import AuditActorType, AuditArea
from app.models.hotel import Property, RatePlan, RoomType
from app.models.promotion import (
    BookingAttribution,
    Promotion,
    PromotionCampaign,
    PromotionCampaignStatus,
    PromotionCode,
    PromotionCodeStatus,
    PromotionDiscountType,
    PromotionManagementOrigin,
    PromotionProperty,
    PromotionRatePlan,
    PromotionRedemption,
    PromotionRedemptionStatus,
    PromotionRoomType,
    PromotionSourceEligibility,
)
from app.schemas.promotion import (
    PromotionCampaignUpdate,
    PromotionCodeCreate,
    PromotionCreate,
    PromotionUpdate,
    PromotionValidationRequest,
    PromotionValidationResult,
)
from app.services.audit import AuditService

_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
_CENT = Decimal("0.01")

# Single lifecycle authority shared by Workspace, platform, and scheduled paths.
CAMPAIGN_TRANSITIONS: dict[PromotionCampaignStatus, set[PromotionCampaignStatus]] = {
    PromotionCampaignStatus.DRAFT: {
        PromotionCampaignStatus.ACTIVE,
        PromotionCampaignStatus.ARCHIVED,
    },
    PromotionCampaignStatus.ACTIVE: {
        PromotionCampaignStatus.PAUSED,
        PromotionCampaignStatus.EXPIRED,
        PromotionCampaignStatus.ARCHIVED,
    },
    PromotionCampaignStatus.PAUSED: {
        PromotionCampaignStatus.ACTIVE,
        PromotionCampaignStatus.EXPIRED,
        PromotionCampaignStatus.ARCHIVED,
    },
    PromotionCampaignStatus.EXPIRED: {PromotionCampaignStatus.ARCHIVED},
    PromotionCampaignStatus.ARCHIVED: set(),
}
CAMPAIGN_ACTIONS = {
    PromotionCampaignStatus.ACTIVE: "PROMOTION_CAMPAIGN_ACTIVATED",
    PromotionCampaignStatus.PAUSED: "PROMOTION_CAMPAIGN_PAUSED",
    PromotionCampaignStatus.EXPIRED: "PROMOTION_CAMPAIGN_EXPIRED",
    PromotionCampaignStatus.ARCHIVED: "PROMOTION_CAMPAIGN_ARCHIVED",
}
CODE_TRANSITIONS: dict[PromotionCodeStatus, set[PromotionCodeStatus]] = {
    PromotionCodeStatus.ACTIVE: {
        PromotionCodeStatus.DISABLED,
        PromotionCodeStatus.ARCHIVED,
    },
    PromotionCodeStatus.DISABLED: {
        PromotionCodeStatus.ACTIVE,
        PromotionCodeStatus.ARCHIVED,
    },
    PromotionCodeStatus.EXHAUSTED: {PromotionCodeStatus.ARCHIVED},
    PromotionCodeStatus.EXPIRED: {PromotionCodeStatus.ARCHIVED},
    PromotionCodeStatus.ARCHIVED: set(),
}
CODE_ACTIONS = {
    PromotionCodeStatus.ACTIVE: "PROMOTION_CODE_ENABLED",
    PromotionCodeStatus.DISABLED: "PROMOTION_CODE_DISABLED",
    PromotionCodeStatus.ARCHIVED: "PROMOTION_CODE_ARCHIVED",
}


class PromotionConflictError(AppError):
    status_code = 409
    code = "PROMOTION_CONFLICT"
    message = "Promotion conflicts with existing data"


class PromotionTransitionError(AppError):
    status_code = 409
    code = "PROMOTION_TRANSITION_INVALID"
    message = "Promotion lifecycle transition is not allowed"


class PromotionRejectedError(AppError):
    status_code = 422
    code = "PROMOTION_INVALID"
    message = "Promotion cannot be applied"

    def __init__(self, reason_code: str):
        super().__init__(details={"reason_code": reason_code})


def normalize_promotion_code(value: str) -> str:
    if value != value.strip() or not value.isascii():
        raise PromotionRejectedError("PROMOTION_NOT_FOUND")
    normalized = value.upper()
    if not _CODE.fullmatch(normalized):
        raise PromotionRejectedError("PROMOTION_NOT_FOUND")
    return normalized


class PromotionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_campaigns(self, workspace_id):
        return list(
            (
                await self.session.execute(
                    select(PromotionCampaign)
                    .where(PromotionCampaign.workspace_id == workspace_id)
                    .order_by(
                        PromotionCampaign.updated_at.desc(), PromotionCampaign.id.desc()
                    )
                )
            ).scalars()
        )

    async def get_campaign(self, workspace_id, campaign_id):
        return await self._campaign(workspace_id, campaign_id)

    async def create_campaign(
        self,
        workspace_id,
        actor_user_id,
        data,
        *,
        origin: PromotionManagementOrigin = PromotionManagementOrigin.WORKSPACE,
        actor_type: AuditActorType | None = None,
        reason: str | None = None,
    ):
        item = PromotionCampaign(
            workspace_id=workspace_id,
            created_by_user_id=actor_user_id,
            status=PromotionCampaignStatus.DRAFT,
            management_origin=origin.value,
            **data.model_dump(),
        )
        self.session.add(item)
        await self.session.flush()
        self._audit(
            workspace_id,
            actor_user_id,
            "PROMOTION_CAMPAIGN_CREATED",
            "PromotionCampaign",
            item.id,
            self._with_reason(
                {"status": item.status.value, "origin": origin.value}, reason
            ),
            actor_type=actor_type,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def update_campaign(
        self,
        workspace_id,
        actor_user_id,
        campaign_id,
        data: PromotionCampaignUpdate,
        *,
        allowed_fields: set[str] | None = None,
        actor_type: AuditActorType | None = None,
        reason: str | None = None,
    ):
        item = await self._campaign(workspace_id, campaign_id, for_update=True)
        if item.status is PromotionCampaignStatus.ARCHIVED:
            raise PromotionTransitionError()
        values = data.model_dump(exclude_unset=True)
        if allowed_fields is not None and set(values) - allowed_fields:
            raise PromotionTransitionError(
                "Field cannot be changed in the current lifecycle state",
                details={"fields": sorted(set(values) - allowed_fields)},
            )
        changed = []
        for key, value in values.items():
            if getattr(item, key) != value:
                setattr(item, key, value)
                changed.append(key)
        if item.valid_from and item.valid_until and item.valid_until <= item.valid_from:
            raise PromotionRejectedError("PROMOTION_VALIDITY_INVALID")
        self._audit(
            workspace_id,
            actor_user_id,
            "PROMOTION_CAMPAIGN_UPDATED",
            "PromotionCampaign",
            item.id,
            self._with_reason({"changed_fields": sorted(changed)}, reason),
            actor_type=actor_type,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def transition_campaign(
        self,
        workspace_id,
        actor_user_id,
        campaign_id,
        target,
        *,
        actor_type: AuditActorType | None = None,
        reason: str | None = None,
        idempotent: bool = False,
    ):
        item = await self._campaign(workspace_id, campaign_id, for_update=True)
        if idempotent and item.status is target:
            await self.session.commit()
            return item
        if target not in CAMPAIGN_TRANSITIONS[item.status]:
            raise PromotionTransitionError(
                details={
                    "current_status": item.status.value,
                    "target_status": target.value,
                }
            )
        now = datetime.now(UTC)
        if (
            target is PromotionCampaignStatus.ACTIVE
            and item.valid_until
            and item.valid_until <= now
        ):
            raise PromotionTransitionError(
                "Campaign validity window has already ended",
                details={"reason_code": "PROMOTION_EXPIRED"},
            )
        previous = item.status
        item.status = target
        if (
            target is PromotionCampaignStatus.ACTIVE
            and item.started_at is None
            and (item.valid_from is None or item.valid_from <= now)
        ):
            item.started_at = now
        self._audit(
            workspace_id,
            actor_user_id,
            CAMPAIGN_ACTIONS[target],
            "PromotionCampaign",
            item.id,
            self._with_reason(
                {"previous_status": previous.value, "new_status": target.value},
                reason,
            ),
            actor_type=actor_type,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def list_promotions(self, workspace_id):
        values = list(
            (
                await self.session.execute(
                    select(Promotion)
                    .where(Promotion.workspace_id == workspace_id)
                    .order_by(Promotion.updated_at.desc(), Promotion.id.desc())
                )
            ).scalars()
        )
        for item in values:
            await self._eligibility(item)
        return values

    async def create_promotion(
        self,
        workspace_id,
        actor_user_id,
        data: PromotionCreate,
        *,
        actor_type: AuditActorType | None = None,
        reason: str | None = None,
    ):
        await self._campaign(workspace_id, data.campaign_id)
        await self._validate_targets(workspace_id, data)
        fields = data.model_dump(
            exclude={"property_ids", "room_type_ids", "rate_plan_ids", "sources"}
        )
        item = Promotion(workspace_id=workspace_id, active=True, **fields)
        self.session.add(item)
        await self.session.flush()
        await self._replace_eligibility(workspace_id, item.id, data)
        self._audit(
            workspace_id,
            actor_user_id,
            "PROMOTION_CREATED",
            "Promotion",
            item.id,
            self._with_reason({"campaign_id": str(item.campaign_id)}, reason),
            actor_type=actor_type,
        )
        await self.session.commit()
        await self.session.refresh(item)
        await self._eligibility(item)
        return item

    async def update_promotion(
        self, workspace_id, actor_user_id, promotion_id, data: PromotionUpdate
    ):
        item = await self._promotion(workspace_id, promotion_id, for_update=True)
        await self._validate_targets(workspace_id, data)
        fields = data.model_dump(
            exclude_unset=True,
            exclude={"property_ids", "room_type_ids", "rate_plan_ids", "sources"},
        )
        changed = []
        for key, value in fields.items():
            if value is not None and getattr(item, key) != value:
                setattr(item, key, value)
                changed.append(key)
        self._validate_merged_rule(item)
        supplied = data.model_fields_set
        if supplied.intersection(
            {"property_ids", "room_type_ids", "rate_plan_ids", "sources"}
        ):
            await self._replace_eligibility(workspace_id, item.id, data)
            changed.append("eligibility")
        self._audit(
            workspace_id,
            actor_user_id,
            "PROMOTION_UPDATED",
            "Promotion",
            item.id,
            {"changed_fields": sorted(set(changed))},
        )
        await self.session.commit()
        await self.session.refresh(item)
        await self._eligibility(item)
        return item

    async def list_codes(self, workspace_id):
        return list(
            (
                await self.session.execute(
                    select(PromotionCode)
                    .where(PromotionCode.workspace_id == workspace_id)
                    .order_by(PromotionCode.updated_at.desc(), PromotionCode.id.desc())
                )
            ).scalars()
        )

    async def create_code(
        self,
        workspace_id,
        actor_user_id,
        data: PromotionCodeCreate,
        *,
        actor_type: AuditActorType | None = None,
        reason: str | None = None,
    ):
        await self._promotion(workspace_id, data.promotion_id)
        normalized = normalize_promotion_code(data.code)
        item = PromotionCode(
            workspace_id=workspace_id,
            promotion_id=data.promotion_id,
            code=normalized,
            normalized_code=normalized,
            status=PromotionCodeStatus.ACTIVE,
            usage_limit=data.usage_limit,
        )
        self.session.add(item)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise PromotionConflictError("Promotion code already exists") from exc
        self._audit(
            workspace_id,
            actor_user_id,
            "PROMOTION_CODE_CREATED",
            "PromotionCode",
            item.id,
            self._with_reason({"code": normalized}, reason),
            actor_type=actor_type,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def transition_code(
        self,
        workspace_id,
        actor_user_id,
        code_id,
        target,
        *,
        actor_type: AuditActorType | None = None,
        reason: str | None = None,
        idempotent: bool = False,
    ):
        item = await self.session.scalar(
            select(PromotionCode)
            .where(
                PromotionCode.workspace_id == workspace_id,
                PromotionCode.id == code_id,
            )
            .with_for_update()
        )
        if item is None:
            raise NotFoundError("Promotion code not found")
        if idempotent and item.status is target:
            await self.session.commit()
            return item
        if target not in CODE_TRANSITIONS[item.status]:
            raise PromotionTransitionError(
                details={
                    "current_status": item.status.value,
                    "target_status": target.value,
                }
            )
        previous = item.status
        item.status = target
        self._audit(
            workspace_id,
            actor_user_id,
            CODE_ACTIONS[target],
            "PromotionCode",
            item.id,
            self._with_reason(
                {"previous_status": previous.value, "new_status": target.value},
                reason,
            ),
            actor_type=actor_type,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def validate(self, workspace_id, data: PromotionValidationRequest):
        normalized = normalize_promotion_code(data.code)
        row = (
            await self.session.execute(
                select(PromotionCode, Promotion, PromotionCampaign)
                .join(
                    Promotion,
                    (Promotion.workspace_id == PromotionCode.workspace_id)
                    & (Promotion.id == PromotionCode.promotion_id),
                )
                .join(
                    PromotionCampaign,
                    (PromotionCampaign.workspace_id == Promotion.workspace_id)
                    & (PromotionCampaign.id == Promotion.campaign_id),
                )
                .where(
                    PromotionCode.workspace_id == workspace_id,
                    PromotionCode.normalized_code == normalized,
                )
            )
        ).first()
        if row is None:
            return self._invalid(data, "PROMOTION_NOT_FOUND")
        code, promotion, campaign = row
        reason = await self._reason(data, code, promotion, campaign)
        if reason:
            return self._invalid(data, reason)
        discount = self.calculate_discount(promotion, data.subtotal)
        return PromotionValidationResult(
            valid=True,
            reason_code=None,
            promotion_id=promotion.id,
            promotion_code_id=code.id,
            campaign_id=campaign.id,
            code=code.code,
            promotion_name=promotion.name,
            discount_type=promotion.discount_type,
            discount_value=promotion.discount_value,
            discount_amount=discount,
            subtotal=data.subtotal,
            final_total=data.subtotal - discount,
            currency=data.currency,
        )

    async def reserve_for_booking(
        self,
        *,
        workspace_id,
        booking_id,
        customer_id,
        hold_expires_at,
        data: PromotionValidationRequest,
        actor_user_id=None,
    ):
        existing = await self.session.scalar(
            select(PromotionRedemption).where(
                PromotionRedemption.workspace_id == workspace_id,
                PromotionRedemption.booking_id == booking_id,
            )
        )
        if existing:
            return existing, None
        normalized = normalize_promotion_code(data.code)
        code = await self.session.scalar(
            select(PromotionCode)
            .where(
                PromotionCode.workspace_id == workspace_id,
                PromotionCode.normalized_code == normalized,
            )
            .with_for_update()
        )
        if code is None:
            raise PromotionRejectedError("PROMOTION_NOT_FOUND")
        # Lock order: code -> redemption rows -> rule. confirm_redemption locks
        # redemption -> rule, and cancel/expire lock inventory -> redemption, so
        # lapsed reservations must be released before the rule lock is taken.
        await self.session.execute(
            update(PromotionRedemption)
            .where(
                PromotionRedemption.workspace_id == workspace_id,
                PromotionRedemption.promotion_id == code.promotion_id,
                PromotionRedemption.status == PromotionRedemptionStatus.RESERVED,
                PromotionRedemption.reserved_until < datetime.now(UTC),
            )
            .values(status=PromotionRedemptionStatus.RELEASED)
        )
        # Rule-wide limits span every code of the rule, so the code lock alone
        # cannot serialize them; usage is counted only after this lock.
        await self.session.execute(
            select(Promotion.id)
            .where(
                Promotion.workspace_id == workspace_id,
                Promotion.id == code.promotion_id,
            )
            .with_for_update()
        )
        result = await self.validate(workspace_id, data)
        if not result.valid:
            raise PromotionRejectedError(result.reason_code)
        redemption = PromotionRedemption(
            workspace_id=workspace_id,
            promotion_id=result.promotion_id,
            promotion_code_id=result.promotion_code_id,
            customer_id=customer_id,
            booking_id=booking_id,
            discount_amount=result.discount_amount,
            currency=result.currency,
            status=PromotionRedemptionStatus.RESERVED,
            reserved_until=hold_expires_at,
        )
        attribution = await self.session.scalar(
            select(BookingAttribution).where(
                BookingAttribution.workspace_id == workspace_id,
                BookingAttribution.booking_id == booking_id,
            )
        )
        if attribution is None:
            attribution = BookingAttribution(
                workspace_id=workspace_id,
                booking_id=booking_id,
                source=data.source,
            )
        attribution.campaign_id = result.campaign_id
        attribution.promotion_id = result.promotion_id
        attribution.promotion_code_id = result.promotion_code_id
        self.session.add_all((redemption, attribution))
        self._audit(
            workspace_id,
            actor_user_id,
            "PROMOTION_APPLIED",
            "Booking",
            booking_id,
            {
                "promotion_id": str(result.promotion_id),
                "promotion_code": result.code,
                "discount_amount": str(result.discount_amount),
                "currency": result.currency,
            },
        )
        await self.session.flush()
        return redemption, result

    async def confirm_redemption(self, workspace_id, booking_id):
        item = await self.session.scalar(
            select(PromotionRedemption)
            .where(
                PromotionRedemption.workspace_id == workspace_id,
                PromotionRedemption.booking_id == booking_id,
            )
            .with_for_update()
        )
        if item is None:
            return None
        if item.status is PromotionRedemptionStatus.CONFIRMED:
            return item
        if item.status is not PromotionRedemptionStatus.RESERVED:
            raise PromotionRejectedError("PROMOTION_USAGE_LIMIT_REACHED")
        await self.session.execute(
            select(Promotion).where(Promotion.id == item.promotion_id).with_for_update()
        )
        item.status = PromotionRedemptionStatus.CONFIRMED
        item.redeemed_at = datetime.now(UTC)
        item.reserved_until = None
        self._audit(
            workspace_id,
            None,
            "PROMOTION_REDEMPTION_CONFIRMED",
            "PromotionRedemption",
            item.id,
            {
                "booking_id": str(booking_id),
                "promotion_id": str(item.promotion_id),
                "discount_amount": str(item.discount_amount),
                "currency": item.currency,
            },
        )
        await self.session.flush()
        return item

    async def release_reservation(self, workspace_id, booking_id):
        item = await self.session.scalar(
            select(PromotionRedemption)
            .where(
                PromotionRedemption.workspace_id == workspace_id,
                PromotionRedemption.booking_id == booking_id,
            )
            .with_for_update()
        )
        if item and item.status is PromotionRedemptionStatus.RESERVED:
            item.status = PromotionRedemptionStatus.RELEASED
            item.reserved_until = None

    async def list_redemptions(self, workspace_id, limit=100):
        return list(
            (
                await self.session.execute(
                    select(PromotionRedemption)
                    .where(PromotionRedemption.workspace_id == workspace_id)
                    .order_by(
                        PromotionRedemption.created_at.desc(),
                        PromotionRedemption.id.desc(),
                    )
                    .limit(limit)
                )
            ).scalars()
        )

    @staticmethod
    def calculate_discount(promotion: Promotion, subtotal: Decimal) -> Decimal:
        if promotion.discount_type is PromotionDiscountType.PERCENTAGE:
            value = subtotal * promotion.discount_value / Decimal("100")
            if promotion.max_discount_amount is not None:
                value = min(value, promotion.max_discount_amount)
        else:
            value = promotion.discount_value
        return min(subtotal, value).quantize(_CENT, rounding=ROUND_HALF_UP)

    async def _reason(self, data, code, promotion, campaign):
        now = datetime.now(UTC)
        if code.status is PromotionCodeStatus.DISABLED:
            return "PROMOTION_INACTIVE"
        if code.status is PromotionCodeStatus.ARCHIVED:
            return "PROMOTION_INACTIVE"
        if code.status is PromotionCodeStatus.EXPIRED:
            return "PROMOTION_EXPIRED"
        if code.status is PromotionCodeStatus.EXHAUSTED:
            return "PROMOTION_USAGE_LIMIT_REACHED"
        if (
            campaign.status is not PromotionCampaignStatus.ACTIVE
            or not promotion.active
        ):
            return "PROMOTION_INACTIVE"
        if campaign.valid_from and now < campaign.valid_from:
            return "PROMOTION_NOT_STARTED"
        if promotion.valid_from and now < promotion.valid_from:
            return "PROMOTION_NOT_STARTED"
        if (campaign.valid_until and now >= campaign.valid_until) or (
            promotion.valid_until and now >= promotion.valid_until
        ):
            return "PROMOTION_EXPIRED"
        if promotion.stay_date_start and data.check_in < promotion.stay_date_start:
            return "PROMOTION_STAY_DATE_NOT_ELIGIBLE"
        if promotion.stay_date_end and data.check_out > promotion.stay_date_end:
            return "PROMOTION_STAY_DATE_NOT_ELIGIBLE"
        if promotion.minimum_subtotal and data.subtotal < promotion.minimum_subtotal:
            return "PROMOTION_MINIMUM_NOT_MET"
        if promotion.currency and data.currency != promotion.currency:
            return "PROMOTION_CURRENCY_MISMATCH"
        for model, field, value, reason in (
            (
                PromotionProperty,
                PromotionProperty.property_id,
                data.property_id,
                "PROMOTION_PROPERTY_NOT_ELIGIBLE",
            ),
            (
                PromotionRoomType,
                PromotionRoomType.room_type_id,
                data.room_type_id,
                "PROMOTION_ROOM_TYPE_NOT_ELIGIBLE",
            ),
            (
                PromotionRatePlan,
                PromotionRatePlan.rate_plan_id,
                data.rate_plan_id,
                "PROMOTION_RATE_PLAN_NOT_ELIGIBLE",
            ),
            (
                PromotionSourceEligibility,
                PromotionSourceEligibility.source,
                data.source,
                "PROMOTION_SOURCE_NOT_ELIGIBLE",
            ),
        ):
            count = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(
                        model.workspace_id == promotion.workspace_id,
                        model.promotion_id == promotion.id,
                    )
                )
                or 0
            )
            if count and not await self.session.scalar(
                select(field).where(
                    model.workspace_id == promotion.workspace_id,
                    model.promotion_id == promotion.id,
                    field == value,
                )
            ):
                return reason
        active = (PromotionRedemption.status == PromotionRedemptionStatus.CONFIRMED) | (
            (PromotionRedemption.status == PromotionRedemptionStatus.RESERVED)
            & (PromotionRedemption.reserved_until >= now)
        )
        usage = (
            await self.session.execute(
                select(
                    func.count(PromotionRedemption.id),
                    func.count(PromotionRedemption.id).filter(
                        PromotionRedemption.promotion_code_id == code.id
                    ),
                ).where(
                    PromotionRedemption.workspace_id == promotion.workspace_id,
                    PromotionRedemption.promotion_id == promotion.id,
                    active,
                )
            )
        ).one()
        rule_used, code_used = int(usage[0]), int(usage[1])
        if (
            promotion.total_usage_limit is not None
            and rule_used >= promotion.total_usage_limit
        ) or (code.usage_limit is not None and code_used >= code.usage_limit):
            return "PROMOTION_USAGE_LIMIT_REACHED"
        if data.customer_id and promotion.per_customer_limit:
            customer_used = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(PromotionRedemption)
                    .where(
                        PromotionRedemption.workspace_id == promotion.workspace_id,
                        PromotionRedemption.promotion_id == promotion.id,
                        PromotionRedemption.customer_id == data.customer_id,
                        active,
                    )
                )
                or 0
            )
            if customer_used >= promotion.per_customer_limit:
                return "PROMOTION_CUSTOMER_LIMIT_REACHED"
        return None

    @staticmethod
    def _invalid(data, reason):
        return PromotionValidationResult(
            valid=False,
            reason_code=reason,
            promotion_id=None,
            promotion_code_id=None,
            campaign_id=None,
            code=None,
            promotion_name=None,
            discount_type=None,
            discount_value=None,
            discount_amount=Decimal("0.00"),
            subtotal=data.subtotal,
            final_total=data.subtotal,
            currency=data.currency,
        )

    async def _campaign(self, workspace_id, campaign_id, for_update=False):
        statement = select(PromotionCampaign).where(
            PromotionCampaign.workspace_id == workspace_id,
            PromotionCampaign.id == campaign_id,
        )
        if for_update:
            statement = statement.with_for_update()
        item = await self.session.scalar(statement)
        if item is None:
            raise NotFoundError("Promotion campaign not found")
        return item

    async def _promotion(self, workspace_id, promotion_id, for_update=False):
        statement = select(Promotion).where(
            Promotion.workspace_id == workspace_id, Promotion.id == promotion_id
        )
        if for_update:
            statement = statement.with_for_update()
        item = await self.session.scalar(statement)
        if item is None:
            raise NotFoundError("Promotion not found")
        return item

    async def _replace_eligibility(self, workspace_id, promotion_id, data):
        for model in (
            PromotionProperty,
            PromotionRoomType,
            PromotionRatePlan,
            PromotionSourceEligibility,
        ):
            await self.session.execute(
                delete(model).where(
                    model.workspace_id == workspace_id,
                    model.promotion_id == promotion_id,
                )
            )
        self.session.add_all(
            [
                PromotionProperty(
                    workspace_id=workspace_id,
                    promotion_id=promotion_id,
                    property_id=value,
                )
                for value in data.property_ids
            ]
            + [
                PromotionRoomType(
                    workspace_id=workspace_id,
                    promotion_id=promotion_id,
                    room_type_id=value,
                )
                for value in data.room_type_ids
            ]
            + [
                PromotionRatePlan(
                    workspace_id=workspace_id,
                    promotion_id=promotion_id,
                    rate_plan_id=value,
                )
                for value in data.rate_plan_ids
            ]
            + [
                PromotionSourceEligibility(
                    workspace_id=workspace_id,
                    promotion_id=promotion_id,
                    source=value,
                )
                for value in data.sources
            ]
        )

    async def _eligibility(self, item):
        async def values(model, field):
            return list(
                (
                    await self.session.execute(
                        select(field).where(
                            model.workspace_id == item.workspace_id,
                            model.promotion_id == item.id,
                        )
                    )
                ).scalars()
            )

        item.property_ids = await values(
            PromotionProperty, PromotionProperty.property_id
        )
        item.room_type_ids = await values(
            PromotionRoomType, PromotionRoomType.room_type_id
        )
        item.rate_plan_ids = await values(
            PromotionRatePlan, PromotionRatePlan.rate_plan_id
        )
        item.sources = await values(
            PromotionSourceEligibility, PromotionSourceEligibility.source
        )

    async def _validate_targets(self, workspace_id, data):
        # Composite foreign keys remain the final workspace-isolation guard;
        # this check turns a foreign or unknown target into a stable 422.
        if data.campaign_id:
            await self._campaign(workspace_id, data.campaign_id)
        for model, ids in (
            (Property, data.property_ids),
            (RoomType, data.room_type_ids),
            (RatePlan, data.rate_plan_ids),
        ):
            wanted = set(ids or [])
            if not wanted:
                continue
            found = int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.workspace_id == workspace_id, model.id.in_(wanted))
                )
                or 0
            )
            if found != len(wanted):
                raise PromotionRejectedError("PROMOTION_TARGET_INVALID")

    @staticmethod
    def _validate_merged_rule(item):
        if (
            item.discount_type is PromotionDiscountType.PERCENTAGE
            and item.discount_value > Decimal("100")
        ):
            raise PromotionRejectedError("PROMOTION_DISCOUNT_INVALID")
        if (
            item.discount_type is PromotionDiscountType.FIXED_AMOUNT
            and not item.currency
        ):
            raise PromotionRejectedError("PROMOTION_CURRENCY_REQUIRED")
        if item.valid_from and item.valid_until and item.valid_until <= item.valid_from:
            raise PromotionRejectedError("PROMOTION_VALIDITY_INVALID")
        if (
            item.stay_date_start
            and item.stay_date_end
            and item.stay_date_end < item.stay_date_start
        ):
            raise PromotionRejectedError("PROMOTION_STAY_DATES_INVALID")

    @staticmethod
    def _with_reason(metadata: dict, reason: str | None) -> dict:
        return {**metadata, "reason": reason} if reason else metadata

    def _audit(
        self,
        workspace_id,
        actor_user_id,
        action,
        resource_type,
        resource_id,
        metadata=None,
        *,
        actor_type: AuditActorType | None = None,
    ):
        AuditService(self.session).record(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type
            or (AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM),
            action=action,
            area=AuditArea.PROMOTIONS,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
