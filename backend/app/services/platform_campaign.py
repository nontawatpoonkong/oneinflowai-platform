"""Platform-operator governance over Workspace-owned promotion campaigns.

Funding boundary: every campaign is owned by exactly one Workspace and its
discount reduces that Workspace's hotel Booking revenue. OneInFlowAI has no
platform-funded discount, settlement, or reimbursement model, so platform
operators may *author drafts* and *reduce* discount exposure (pause, expire,
archive, disable), but cannot activate, resume, or re-enable anything. Those
decisions stay with the Workspace that bears the discount. All state changes
delegate to ``PromotionService`` so there is one lifecycle authority.
"""

import enum
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Date, cast, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.audit import AuditActorType, AuditArea, WorkspaceAuditEvent
from app.models.booking import Booking, BookingStatus
from app.models.hotel import Property, RatePlan, RoomType
from app.models.promotion import (
    BookingAttribution,
    Promotion,
    PromotionCampaign,
    PromotionCampaignStatus,
    PromotionCode,
    PromotionCodeStatus,
    PromotionManagementOrigin,
    PromotionRedemption,
    PromotionRedemptionStatus,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceStatus
from app.schemas.platform import (
    PlatformCampaignCreate,
    PlatformCampaignUpdate,
    PlatformCodeCreate,
    PlatformRuleCreate,
)
from app.schemas.promotion import (
    PromotionCampaignCreate,
    PromotionCampaignUpdate,
    PromotionCodeCreate,
    PromotionCreate,
)
from app.services.audit import AuditService
from app.services.promotion import CAMPAIGN_TRANSITIONS, PromotionService
from app.services.promotion_lifecycle import PromotionLifecycleService

MAX_ANALYTICS_RANGE = timedelta(days=366)
# One PLATFORM_CATALOG_VIEWED event per admin and campaign per window, so
# paging, searching, and filtering inside one targeting task do not flood
# the append-only audit table.
CATALOG_AUDIT_WINDOW = timedelta(minutes=15)
_CONFIRM_FIELDS = {"reason", "confirmed"}
DRAFT_EDITABLE = {"name", "description", "valid_from", "valid_until"}
LIVE_EDITABLE = {"name", "description"}
PLATFORM_CAMPAIGN_TARGETS = {
    PromotionCampaignStatus.PAUSED,
    PromotionCampaignStatus.EXPIRED,
    PromotionCampaignStatus.ARCHIVED,
}
PLATFORM_CODE_TARGETS = {PromotionCodeStatus.DISABLED, PromotionCodeStatus.ARCHIVED}
FUNDING = {
    "owner": "WORKSPACE",
    "discount_borne_by": "WORKSPACE",
    "platform_funded": False,
    "cross_workspace_redemption": False,
    "note": (
        "Discounts reduce the owning Workspace's hotel Booking revenue. "
        "No platform-funded settlement model exists."
    ),
}


class CatalogTargetKind(enum.StrEnum):
    PROPERTY = "property"
    ROOM_TYPE = "room_type"
    RATE_PLAN = "rate_plan"


_CATALOG_MODELS = {
    CatalogTargetKind.PROPERTY: Property,
    CatalogTargetKind.ROOM_TYPE: RoomType,
    CatalogTargetKind.RATE_PLAN: RatePlan,
}


class PlatformCatalogFilterError(AppError):
    status_code = 422
    code = "PLATFORM_CATALOG_FILTER_INVALID"
    message = (
        "property_id applies to room types and rate plans; room_type_id applies "
        "to rate plans only"
    )


class PlatformCampaignError(AppError):
    status_code = 409
    code = "PLATFORM_CAMPAIGN_OPERATION_INVALID"
    message = "Platform campaign operation is not allowed"


class PlatformCampaignActivationError(AppError):
    status_code = 409
    code = "PLATFORM_CAMPAIGN_ACTIVATION_REQUIRES_WORKSPACE"
    message = (
        "Only the owning Workspace can activate, resume, or re-enable a "
        "discount it funds"
    )


class PlatformCampaignService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.promotions = PromotionService(session)

    # ------------------------------------------------------------------ writes

    async def create_campaign(
        self, actor: User, data: PlatformCampaignCreate
    ) -> PromotionCampaign:
        workspace = await self.session.get(Workspace, data.workspace_id)
        if workspace is None:
            raise NotFoundError("Workspace not found")
        if workspace.status != WorkspaceStatus.ACTIVE:
            raise PlatformCampaignError("Workspace is not active")
        payload = PromotionCampaignCreate(
            **data.model_dump(exclude=_CONFIRM_FIELDS | {"workspace_id"})
        )
        return await self.promotions.create_campaign(
            workspace.id,
            actor.id,
            payload,
            origin=PromotionManagementOrigin.PLATFORM,
            actor_type=AuditActorType.PLATFORM_ADMIN,
            reason=data.reason,
        )

    async def update_campaign(
        self, actor: User, campaign_id: uuid.UUID, data: PlatformCampaignUpdate
    ) -> PromotionCampaign:
        campaign = await self._campaign(campaign_id)
        await self._require_active_workspace(campaign.workspace_id)
        allowed = (
            DRAFT_EDITABLE
            if campaign.status is PromotionCampaignStatus.DRAFT
            else LIVE_EDITABLE
        )
        payload = PromotionCampaignUpdate(
            **data.model_dump(exclude_unset=True, exclude=_CONFIRM_FIELDS)
        )
        return await self.promotions.update_campaign(
            campaign.workspace_id,
            actor.id,
            campaign.id,
            payload,
            allowed_fields=allowed,
            actor_type=AuditActorType.PLATFORM_ADMIN,
            reason=data.reason,
        )

    async def create_rule(
        self, actor: User, campaign_id: uuid.UUID, data: PlatformRuleCreate
    ) -> Promotion:
        campaign = await self._draft_campaign(campaign_id)
        await self._require_active_workspace(campaign.workspace_id)
        payload = PromotionCreate(
            **data.model_dump(exclude=_CONFIRM_FIELDS | {"campaign_id"}),
            campaign_id=campaign.id,
        )
        try:
            return await self.promotions.create_promotion(
                campaign.workspace_id,
                actor.id,
                payload,
                actor_type=AuditActorType.PLATFORM_ADMIN,
                reason=data.reason,
            )
        except IntegrityError as exc:
            # Composite foreign keys reject catalog IDs from another Workspace.
            await self.session.rollback()
            raise PlatformCampaignError(
                "Eligibility targets must belong to the campaign Workspace"
            ) from exc

    async def create_code(
        self, actor: User, campaign_id: uuid.UUID, data: PlatformCodeCreate
    ) -> PromotionCode:
        campaign = await self._draft_campaign(campaign_id)
        await self._require_active_workspace(campaign.workspace_id)
        rule = await self.session.scalar(
            select(Promotion).where(
                Promotion.workspace_id == campaign.workspace_id,
                Promotion.campaign_id == campaign.id,
                Promotion.id == data.promotion_id,
            )
        )
        if rule is None:
            raise NotFoundError("Promotion rule not found in this campaign")
        return await self.promotions.create_code(
            campaign.workspace_id,
            actor.id,
            PromotionCodeCreate(**data.model_dump(exclude=_CONFIRM_FIELDS)),
            actor_type=AuditActorType.PLATFORM_ADMIN,
            reason=data.reason,
        )

    async def transition_campaign(
        self,
        actor: User,
        campaign_id: uuid.UUID,
        target: PromotionCampaignStatus,
        reason: str,
    ) -> PromotionCampaign:
        if target not in PLATFORM_CAMPAIGN_TARGETS:
            raise PlatformCampaignActivationError()
        campaign = await self._campaign(campaign_id)
        return await self.promotions.transition_campaign(
            campaign.workspace_id,
            actor.id,
            campaign.id,
            target,
            actor_type=AuditActorType.PLATFORM_ADMIN,
            reason=reason,
            idempotent=True,
        )

    async def transition_code(
        self,
        actor: User,
        code_id: uuid.UUID,
        target: PromotionCodeStatus,
        reason: str,
    ) -> PromotionCode:
        if target not in PLATFORM_CODE_TARGETS:
            raise PlatformCampaignActivationError()
        code = await self.session.scalar(
            select(PromotionCode).where(PromotionCode.id == code_id)
        )
        if code is None:
            raise NotFoundError("Promotion code not found")
        return await self.promotions.transition_code(
            code.workspace_id,
            actor.id,
            code.id,
            target,
            actor_type=AuditActorType.PLATFORM_ADMIN,
            reason=reason,
            idempotent=True,
        )

    # ------------------------------------------------------------------- reads

    async def list_campaigns(
        self,
        *,
        page: int,
        page_size: int,
        workspace_id: uuid.UUID | None = None,
        status: PromotionCampaignStatus | None = None,
        origin: PromotionManagementOrigin | None = None,
        search: str | None = None,
    ) -> dict:
        filters = []
        if workspace_id:
            filters.append(PromotionCampaign.workspace_id == workspace_id)
        if status:
            filters.append(PromotionCampaign.status == status)
        if origin:
            filters.append(PromotionCampaign.management_origin == origin.value)
        if search:
            pattern = f"%{_escape_like(search)}%"
            filters.append(
                or_(
                    PromotionCampaign.name.ilike(pattern, escape="\\"),
                    Workspace.name.ilike(pattern, escape="\\"),
                )
            )
        now = datetime.now(UTC)
        code_count = (
            select(func.count(PromotionCode.id))
            .join(
                Promotion,
                (Promotion.workspace_id == PromotionCode.workspace_id)
                & (Promotion.id == PromotionCode.promotion_id),
            )
            .where(Promotion.campaign_id == PromotionCampaign.id)
            .correlate(PromotionCampaign)
            .scalar_subquery()
        )

        def redemptions(*conditions):
            return (
                select(func.count(PromotionRedemption.id))
                .join(
                    Promotion,
                    (Promotion.workspace_id == PromotionRedemption.workspace_id)
                    & (Promotion.id == PromotionRedemption.promotion_id),
                )
                .where(Promotion.campaign_id == PromotionCampaign.id, *conditions)
                .correlate(PromotionCampaign)
                .scalar_subquery()
            )

        stmt = (
            select(
                PromotionCampaign,
                Workspace.name,
                code_count,
                redemptions(
                    PromotionRedemption.status == PromotionRedemptionStatus.CONFIRMED
                ),
                redemptions(
                    PromotionRedemption.status == PromotionRedemptionStatus.RESERVED,
                    PromotionRedemption.reserved_until >= now,
                ),
            )
            .join(Workspace, Workspace.id == PromotionCampaign.workspace_id)
            .where(*filters)
        )
        total = await self._total(stmt)
        rows = (
            await self.session.execute(
                stmt.order_by(
                    PromotionCampaign.updated_at.desc(), PromotionCampaign.id.desc()
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return _page(
            [
                {
                    **_campaign_brief(campaign),
                    "workspace": workspace_name,
                    "codes": int(codes),
                    "confirmed_uses": int(confirmed),
                    "active_reservations": int(reserved),
                }
                for campaign, workspace_name, codes, confirmed, reserved in rows
            ],
            total,
            page,
            page_size,
        )

    async def list_codes(
        self,
        *,
        page: int,
        page_size: int,
        workspace_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
        status: PromotionCodeStatus | None = None,
        search: str | None = None,
    ) -> dict:
        filters = []
        if workspace_id:
            filters.append(PromotionCode.workspace_id == workspace_id)
        if campaign_id:
            filters.append(PromotionCampaign.id == campaign_id)
        if status:
            filters.append(PromotionCode.status == status)
        if search:
            filters.append(
                PromotionCode.normalized_code.like(
                    f"{_escape_like(search.strip().upper())}%", escape="\\"
                )
            )
        now = datetime.now(UTC)
        active = (PromotionRedemption.status == PromotionRedemptionStatus.CONFIRMED) | (
            (PromotionRedemption.status == PromotionRedemptionStatus.RESERVED)
            & (PromotionRedemption.reserved_until >= now)
        )

        def uses(*conditions):
            return (
                select(func.count(PromotionRedemption.id))
                .where(
                    PromotionRedemption.workspace_id == PromotionCode.workspace_id,
                    PromotionRedemption.promotion_code_id == PromotionCode.id,
                    *conditions,
                )
                .correlate(PromotionCode)
                .scalar_subquery()
            )

        rule_uses = (
            select(func.count(PromotionRedemption.id))
            .where(
                PromotionRedemption.workspace_id == PromotionCode.workspace_id,
                PromotionRedemption.promotion_id == PromotionCode.promotion_id,
                active,
            )
            .correlate(PromotionCode)
            .scalar_subquery()
        )

        stmt = (
            select(
                PromotionCode,
                Promotion,
                PromotionCampaign,
                Workspace.name,
                uses(PromotionRedemption.status == PromotionRedemptionStatus.CONFIRMED),
                uses(active),
                rule_uses,
            )
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
            .join(Workspace, Workspace.id == PromotionCode.workspace_id)
            .where(*filters)
        )
        total = await self._total(stmt)
        rows = (
            await self.session.execute(
                stmt.order_by(PromotionCode.updated_at.desc(), PromotionCode.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return _page(
            [
                _code_brief(code, promotion, confirmed, counted, rule_counted)
                | {
                    "workspace_id": code.workspace_id,
                    "workspace": workspace_name,
                    "campaign": {
                        "id": campaign.id,
                        "name": campaign.name,
                        "status": campaign.status,
                    },
                }
                for (
                    code,
                    promotion,
                    campaign,
                    workspace_name,
                    confirmed,
                    counted,
                    rule_counted,
                ) in rows
            ],
            total,
            page,
            page_size,
        )

    async def campaign_detail(self, campaign_id: uuid.UUID) -> dict:
        campaign = await self._campaign(campaign_id)
        workspace = await self.session.get(Workspace, campaign.workspace_id)
        workspace_active = workspace.status == WorkspaceStatus.ACTIVE
        rules = list(
            (
                await self.session.execute(
                    select(Promotion)
                    .where(
                        Promotion.workspace_id == campaign.workspace_id,
                        Promotion.campaign_id == campaign.id,
                    )
                    .order_by(Promotion.created_at, Promotion.id)
                    .limit(100)
                )
            ).scalars()
        )
        for rule in rules:
            await self.promotions._eligibility(rule)
        codes = await self.list_codes(page=1, page_size=100, campaign_id=campaign.id)
        redemption_rows = (
            await self.session.execute(
                select(
                    PromotionRedemption.status,
                    PromotionRedemption.currency,
                    func.count(PromotionRedemption.id),
                    func.coalesce(func.sum(PromotionRedemption.discount_amount), 0),
                )
                .join(
                    Promotion,
                    (Promotion.workspace_id == PromotionRedemption.workspace_id)
                    & (Promotion.id == PromotionRedemption.promotion_id),
                )
                .where(Promotion.campaign_id == campaign.id)
                .group_by(PromotionRedemption.status, PromotionRedemption.currency)
                .order_by(PromotionRedemption.status, PromotionRedemption.currency)
            )
        ).all()
        value_rows = (
            await self.session.execute(
                select(
                    Booking.currency,
                    func.count(Booking.id),
                    func.coalesce(func.sum(Booking.subtotal), 0),
                    func.coalesce(func.sum(Booking.discount_amount), 0),
                    func.coalesce(func.sum(Booking.total_amount), 0),
                )
                .join(
                    BookingAttribution,
                    (BookingAttribution.workspace_id == Booking.workspace_id)
                    & (BookingAttribution.booking_id == Booking.id),
                )
                .where(
                    BookingAttribution.campaign_id == campaign.id,
                    Booking.status == BookingStatus.CONFIRMED,
                )
                .group_by(Booking.currency)
                .order_by(Booking.currency)
            )
        ).all()
        resource_ids = (
            [campaign.id]
            + [rule.id for rule in rules]
            + [item["id"] for item in codes["items"]]
        )
        audit_rows = (
            await self.session.execute(
                select(WorkspaceAuditEvent, User.email)
                .outerjoin(User, User.id == WorkspaceAuditEvent.actor_user_id)
                .where(
                    WorkspaceAuditEvent.workspace_id == campaign.workspace_id,
                    WorkspaceAuditEvent.resource_id.in_(resource_ids),
                )
                .order_by(
                    WorkspaceAuditEvent.occurred_at.desc(),
                    WorkspaceAuditEvent.id.desc(),
                )
                .limit(50)
            )
        ).all()
        return {
            "campaign": _campaign_brief(campaign),
            "workspace": {
                "id": workspace.id,
                "name": workspace.name,
                "status": workspace.status,
            },
            "funding": FUNDING,
            "allowed_operations": self._allowed_operations(
                campaign, workspace_active=workspace_active
            ),
            "editable_fields": sorted(
                set()
                if not workspace_active
                else DRAFT_EDITABLE
                if campaign.status is PromotionCampaignStatus.DRAFT
                else LIVE_EDITABLE
                if campaign.status is not PromotionCampaignStatus.ARCHIVED
                else set()
            ),
            "rules": [_rule_brief(rule) for rule in rules],
            "target_labels": await self._target_labels(campaign.workspace_id, rules),
            "codes": codes["items"],
            "redemptions": [
                {
                    "status": status,
                    "currency": currency,
                    "count": int(count),
                    "discount_amount": amount,
                }
                for status, currency, count, amount in redemption_rows
            ],
            "confirmed_booking_value": [
                {
                    "currency": currency,
                    "bookings": int(count),
                    "gross_amount": gross,
                    "discount_granted": discount,
                    "net_amount": net,
                }
                for currency, count, gross, discount, net in value_rows
            ],
            "audit": [
                {
                    "id": event.id,
                    "action": event.action,
                    "actor_type": event.actor_type,
                    "actor_email": email,
                    "resource_type": event.resource_type,
                    "resource_id": event.resource_id,
                    "result": event.result,
                    "safe_metadata": event.safe_metadata,
                    "occurred_at": event.occurred_at,
                }
                for event, email in audit_rows
            ],
        }

    async def analytics(
        self, *, start: datetime, end: datetime, stale_after_seconds: int
    ) -> dict:
        now = datetime.now(UTC)
        campaign_status = dict(
            (
                await self.session.execute(
                    select(PromotionCampaign.status, func.count()).group_by(
                        PromotionCampaign.status
                    )
                )
            ).all()
        )
        code_status = dict(
            (
                await self.session.execute(
                    select(PromotionCode.status, func.count()).group_by(
                        PromotionCode.status
                    )
                )
            ).all()
        )
        origin_rows = dict(
            (
                await self.session.execute(
                    select(PromotionCampaign.management_origin, func.count()).group_by(
                        PromotionCampaign.management_origin
                    )
                )
            ).all()
        )
        # Reservation funnel for redemptions created (at Hold time) in range.
        lapsed = (PromotionRedemption.status == PromotionRedemptionStatus.RESERVED) & (
            PromotionRedemption.reserved_until < now
        )
        funnel_row = (
            await self.session.execute(
                select(
                    func.count(PromotionRedemption.id),
                    func.count(PromotionRedemption.id).filter(
                        PromotionRedemption.status
                        == PromotionRedemptionStatus.CONFIRMED
                    ),
                    func.count(PromotionRedemption.id).filter(
                        (
                            PromotionRedemption.status
                            == PromotionRedemptionStatus.RELEASED
                        )
                        | lapsed
                    ),
                    func.count(PromotionRedemption.id).filter(
                        (
                            PromotionRedemption.status
                            == PromotionRedemptionStatus.RESERVED
                        )
                        & (PromotionRedemption.reserved_until >= now)
                    ),
                ).where(
                    PromotionRedemption.created_at >= start,
                    PromotionRedemption.created_at < end,
                )
            )
        ).one()
        confirmed = (
            PromotionRedemption.status == PromotionRedemptionStatus.CONFIRMED,
            PromotionRedemption.redeemed_at >= start,
            PromotionRedemption.redeemed_at < end,
            Booking.status == BookingStatus.CONFIRMED,
        )
        joined = select(PromotionRedemption).join(
            Booking,
            (Booking.workspace_id == PromotionRedemption.workspace_id)
            & (Booking.id == PromotionRedemption.booking_id),
        )
        money = (
            await self.session.execute(
                joined.with_only_columns(
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.coalesce(func.sum(Booking.subtotal), 0),
                    func.coalesce(func.sum(Booking.discount_amount), 0),
                    func.coalesce(func.sum(Booking.total_amount), 0),
                )
                .where(*confirmed)
                .group_by(Booking.currency)
                .order_by(Booking.currency)
            )
        ).all()
        day = cast(func.timezone("UTC", PromotionRedemption.redeemed_at), Date)
        trend = (
            await self.session.execute(
                joined.with_only_columns(
                    day.label("day"),
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.coalesce(func.sum(Booking.discount_amount), 0),
                )
                .where(*confirmed)
                .group_by(day, Booking.currency)
                .order_by(day, Booking.currency)
            )
        ).all()
        by_workspace = (
            await self.session.execute(
                joined.with_only_columns(
                    Workspace.id,
                    Workspace.name,
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.coalesce(func.sum(Booking.discount_amount), 0),
                    func.coalesce(func.sum(Booking.total_amount), 0),
                )
                .join(Workspace, Workspace.id == PromotionRedemption.workspace_id)
                .where(*confirmed)
                .group_by(Workspace.id, Workspace.name, Booking.currency)
                .order_by(func.count(PromotionRedemption.id).desc(), Workspace.name)
                .limit(25)
            )
        ).all()
        by_campaign = (
            await self.session.execute(
                joined.with_only_columns(
                    PromotionCampaign.id,
                    PromotionCampaign.name,
                    Workspace.name,
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.coalesce(func.sum(Booking.discount_amount), 0),
                    func.coalesce(func.sum(Booking.total_amount), 0),
                )
                .join(
                    Promotion,
                    (Promotion.workspace_id == PromotionRedemption.workspace_id)
                    & (Promotion.id == PromotionRedemption.promotion_id),
                )
                .join(
                    PromotionCampaign,
                    (PromotionCampaign.workspace_id == Promotion.workspace_id)
                    & (PromotionCampaign.id == Promotion.campaign_id),
                )
                .join(Workspace, Workspace.id == PromotionCampaign.workspace_id)
                .where(*confirmed)
                .group_by(
                    PromotionCampaign.id,
                    PromotionCampaign.name,
                    Workspace.name,
                    Booking.currency,
                )
                .order_by(func.count(PromotionRedemption.id).desc())
                .limit(25)
            )
        ).all()
        by_source = (
            await self.session.execute(
                joined.with_only_columns(
                    BookingAttribution.source,
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.coalesce(func.sum(Booking.discount_amount), 0),
                )
                .join(
                    BookingAttribution,
                    (BookingAttribution.workspace_id == Booking.workspace_id)
                    & (BookingAttribution.booking_id == Booking.id),
                )
                .where(*confirmed)
                .group_by(BookingAttribution.source, Booking.currency)
                .order_by(func.count(PromotionRedemption.id).desc())
            )
        ).all()
        return {
            "range": {"start": start, "end": end, "timezone": "UTC"},
            "campaigns_by_status": _counts(campaign_status, PromotionCampaignStatus),
            "codes_by_status": _counts(code_status, PromotionCodeStatus),
            "campaigns_by_origin": {
                origin.value: int(origin_rows.get(origin.value, 0))
                for origin in PromotionManagementOrigin
            },
            "validations": {
                "available": False,
                "reason": (
                    "Code validation is a stateless preview and attempts are "
                    "not persisted."
                ),
            },
            "reservation_funnel": {
                "reserved": int(funnel_row[0]),
                "confirmed": int(funnel_row[1]),
                "released": int(funnel_row[2]),
                "active_reservations": int(funnel_row[3]),
                "definition": (
                    "Redemptions reserved at Booking Hold time within the range, "
                    "by current outcome. Lapsed reservations count as released."
                ),
            },
            "confirmed_by_currency": [
                {
                    "currency": currency,
                    "redemptions": int(count),
                    "gross_amount": gross,
                    "discount_granted": discount,
                    "net_amount": net,
                }
                for currency, count, gross, discount, net in money
            ],
            "daily_trend": [
                {
                    "date": value.isoformat(),
                    "currency": currency,
                    "redemptions": int(count),
                    "discount_granted": discount,
                }
                for value, currency, count, discount in trend
            ],
            "top_workspaces": [
                {
                    "workspace_id": workspace_id,
                    "workspace": name,
                    "currency": currency,
                    "redemptions": int(count),
                    "discount_granted": discount,
                    "net_amount": net,
                }
                for workspace_id, name, currency, count, discount, net in by_workspace
            ],
            "top_campaigns": [
                {
                    "campaign_id": campaign_id,
                    "campaign": name,
                    "workspace": workspace_name,
                    "currency": currency,
                    "redemptions": int(count),
                    "discount_granted": discount,
                    "net_amount": net,
                }
                for (
                    campaign_id,
                    name,
                    workspace_name,
                    currency,
                    count,
                    discount,
                    net,
                ) in by_campaign
            ],
            "by_source": [
                {
                    "source": source,
                    "currency": currency,
                    "redemptions": int(count),
                    "discount_granted": discount,
                }
                for source, currency, count, discount in by_source
            ],
            "campaign_cost": {
                "available": False,
                "reason": (
                    "Discount granted is Workspace hotel revenue forgone, not "
                    "platform cost. No platform funding or ROI data exists."
                ),
            },
            "lifecycle": await PromotionLifecycleService(self.session).status(
                stale_after_seconds=stale_after_seconds
            ),
            "definition": (
                "Confirmed metrics count CONFIRMED redemptions of CONFIRMED "
                "Bookings by redemption time (UTC). Amounts are never summed "
                "across currencies."
            ),
        }

    # ---------------------------------------------------------- catalog reads

    async def catalog_targets(
        self,
        actor: User,
        campaign_id: uuid.UUID,
        *,
        kind: CatalogTargetKind,
        page: int,
        page_size: int,
        property_id: uuid.UUID | None = None,
        room_type_id: uuid.UUID | None = None,
        search: str | None = None,
        active_only: bool = True,
    ) -> dict:
        """Page through the campaign Workspace's targetable catalog.

        The Workspace is always derived from the campaign, never from the
        client, and only whitelisted catalog fields leave this method. Every
        read is audited in the owning Workspace.
        """

        campaign = await self._campaign(campaign_id)
        workspace_id = campaign.workspace_id
        # Catalog targets only serve rule authoring, which is DRAFT-only, and
        # a suspended tenant's catalog is not browsed from the console.
        if campaign.status is not PromotionCampaignStatus.DRAFT:
            raise PlatformCampaignError(
                "Catalog targets are only available for DRAFT campaigns",
                details={"reason_code": "CAMPAIGN_NOT_DRAFT"},
            )
        workspace = await self.session.get(Workspace, workspace_id)
        if workspace is None or workspace.status != WorkspaceStatus.ACTIVE:
            raise PlatformCampaignError(
                "Catalog targets are only available for active Workspaces",
                details={"reason_code": "WORKSPACE_NOT_ACTIVE"},
            )
        model = _CATALOG_MODELS[kind]
        if (property_id and kind is CatalogTargetKind.PROPERTY) or (
            room_type_id and kind is not CatalogTargetKind.RATE_PLAN
        ):
            raise PlatformCatalogFilterError()
        if property_id and not await self._in_workspace(
            Property, workspace_id, property_id
        ):
            raise NotFoundError("Hotel property not found")
        if room_type_id and not await self._in_workspace(
            RoomType, workspace_id, room_type_id
        ):
            raise NotFoundError("Hotel room type not found")
        filters = [model.workspace_id == workspace_id]
        if property_id:
            filters.append(model.property_id == property_id)
        if room_type_id:
            filters.append(model.room_type_id == room_type_id)
        stmt = select(model)
        if active_only:
            filters.append(model.active.is_(True))
            # A target under an inactive parent cannot be booked, so it is not
            # offered either. Joins follow the composite Workspace-scoped keys.
            if kind is not CatalogTargetKind.PROPERTY:
                stmt = stmt.join(
                    Property,
                    (Property.workspace_id == model.workspace_id)
                    & (Property.id == model.property_id),
                )
                filters.append(Property.active.is_(True))
            if kind is CatalogTargetKind.RATE_PLAN:
                stmt = stmt.join(
                    RoomType,
                    (RoomType.workspace_id == model.workspace_id)
                    & (RoomType.property_id == model.property_id)
                    & (RoomType.id == model.room_type_id),
                )
                filters.append(RoomType.active.is_(True))
        if search:
            pattern = f"%{_escape_like(search.strip())}%"
            columns = [model.name.ilike(pattern, escape="\\")]
            if kind is not CatalogTargetKind.PROPERTY:
                columns.append(model.code.ilike(pattern, escape="\\"))
            filters.append(or_(*columns))
        stmt = stmt.where(*filters).order_by(model.name, model.id)
        total = await self._total(stmt)
        rows = list(
            (
                await self.session.execute(
                    stmt.offset((page - 1) * page_size).limit(page_size)
                )
            ).scalars()
        )
        await self._record_catalog_view(
            actor,
            campaign,
            {
                "campaign_id": str(campaign.id),
                "kind": kind.value,
                "page": page,
                "page_size": page_size,
                "property_id": str(property_id) if property_id else None,
                "room_type_id": str(room_type_id) if room_type_id else None,
                "searched": bool(search),
                "active_only": active_only,
                "returned": len(rows),
                "window_seconds": int(CATALOG_AUDIT_WINDOW.total_seconds()),
            },
        )
        await self.session.commit()
        return _page(
            [_catalog_brief(kind, row) for row in rows], total, page, page_size
        )

    async def _record_catalog_view(
        self, actor: User, campaign: PromotionCampaign, metadata: dict
    ) -> None:
        """Append one view event per admin and campaign per audit window.

        The event marks the start of an access window; later reads inside the
        window are covered by it. A transaction-scoped advisory lock makes the
        check-then-insert exact under concurrent reads. Rows are never updated.
        """

        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"platform-catalog-view:{actor.id}:{campaign.id}"},
        )
        since = datetime.now(UTC) - CATALOG_AUDIT_WINDOW
        recent = await self.session.scalar(
            select(WorkspaceAuditEvent.id)
            .where(
                WorkspaceAuditEvent.workspace_id == campaign.workspace_id,
                WorkspaceAuditEvent.action == "PLATFORM_CATALOG_VIEWED",
                WorkspaceAuditEvent.actor_user_id == actor.id,
                WorkspaceAuditEvent.occurred_at > since,
                WorkspaceAuditEvent.safe_metadata["campaign_id"].astext
                == str(campaign.id),
            )
            .limit(1)
        )
        if recent is not None:
            return
        AuditService(self.session).record(
            workspace_id=campaign.workspace_id,
            actor_user_id=actor.id,
            actor_type=AuditActorType.PLATFORM_ADMIN,
            action="PLATFORM_CATALOG_VIEWED",
            area=AuditArea.PROMOTIONS,
            # No resource_id: catalog reads must not crowd the campaign's own
            # audit trail, which is keyed by campaign/rule/code IDs.
            resource_type="HotelCatalog",
            metadata=metadata,
        )

    # ----------------------------------------------------------------- helpers

    async def _in_workspace(self, model, workspace_id, item_id) -> bool:
        return (
            await self.session.scalar(
                select(model.id).where(
                    model.workspace_id == workspace_id, model.id == item_id
                )
            )
            is not None
        )

    async def _target_labels(self, workspace_id, rules: list[Promotion]) -> dict:
        wanted = {
            Property: set(),
            RoomType: set(),
            RatePlan: set(),
        }
        for rule in rules:
            wanted[Property].update(rule.property_ids or [])
            wanted[RoomType].update(rule.room_type_ids or [])
            wanted[RatePlan].update(rule.rate_plan_ids or [])
        labels: dict[str, dict] = {}
        for model, ids in wanted.items():
            if not ids:
                continue
            rows = (
                await self.session.execute(
                    select(model.id, model.name, model.active).where(
                        model.workspace_id == workspace_id, model.id.in_(ids)
                    )
                )
            ).all()
            for item_id, name, active in rows:
                labels[str(item_id)] = {"name": name, "active": active}
        return labels

    @staticmethod
    def _allowed_operations(
        campaign: PromotionCampaign, *, workspace_active: bool = True
    ) -> list[str]:
        verbs = {
            PromotionCampaignStatus.PAUSED: "pause",
            PromotionCampaignStatus.EXPIRED: "expire",
            PromotionCampaignStatus.ARCHIVED: "archive",
        }
        return [
            verbs[target]
            for target in (
                PromotionCampaignStatus.PAUSED,
                PromotionCampaignStatus.EXPIRED,
                PromotionCampaignStatus.ARCHIVED,
            )
            if target in CAMPAIGN_TRANSITIONS[campaign.status]
        ] + (
            ["add_rule", "add_code"]
            if campaign.status is PromotionCampaignStatus.DRAFT and workspace_active
            else []
        )

    async def _require_active_workspace(self, workspace_id: uuid.UUID) -> None:
        """Authoring writes need an ACTIVE Workspace.

        Exposure-reducing transitions (pause, expire, archive, disable) do not
        call this, so operators can still contain a suspended tenant's
        discounts.
        """

        workspace = await self.session.get(Workspace, workspace_id)
        if workspace is None or workspace.status != WorkspaceStatus.ACTIVE:
            raise PlatformCampaignError(
                "Workspace is not active",
                details={"reason_code": "WORKSPACE_NOT_ACTIVE"},
            )

    async def _campaign(self, campaign_id: uuid.UUID) -> PromotionCampaign:
        item = await self.session.scalar(
            select(PromotionCampaign).where(PromotionCampaign.id == campaign_id)
        )
        if item is None:
            raise NotFoundError("Promotion campaign not found")
        return item

    async def _draft_campaign(self, campaign_id: uuid.UUID) -> PromotionCampaign:
        item = await self._campaign(campaign_id)
        if item.status is not PromotionCampaignStatus.DRAFT:
            raise PlatformCampaignError(
                "Rules and codes can only be added while the campaign is DRAFT",
                details={"current_status": item.status.value},
            )
        return item

    async def _total(self, stmt) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )


def validate_range(start: datetime | None, end: datetime | None):
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=30)
    if start.tzinfo is None or end.tzinfo is None:
        raise PlatformRangeError()
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if start >= end or end - start > MAX_ANALYTICS_RANGE:
        raise PlatformRangeError()
    return start, end


class PlatformRangeError(AppError):
    status_code = 422
    code = "ANALYTICS_RANGE_INVALID"
    message = "Analytics range must be timezone-aware and at most 366 days"


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _counts(rows: dict, enum_cls) -> dict[str, int]:
    return {item.value: int(rows.get(item, 0)) for item in enum_cls}


def _page(items: list[dict], total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": -(-total // page_size) if total else 0,
    }


def _campaign_brief(item: PromotionCampaign) -> dict:
    return {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "name": item.name,
        "description": item.description,
        "status": item.status,
        "origin": item.management_origin,
        "funding": "WORKSPACE",
        "valid_from": item.valid_from,
        "valid_until": item.valid_until,
        "started_at": item.started_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _catalog_brief(kind: CatalogTargetKind, item) -> dict:
    # Explicit whitelist: descriptions, prices, and policies stay out of the
    # platform payload; catalog rows carry no guest data.
    return {
        "id": item.id,
        "kind": kind.value,
        "name": item.name,
        "code": getattr(item, "code", None),
        "active": item.active,
        "property_id": getattr(item, "property_id", None),
        "room_type_id": getattr(item, "room_type_id", None),
        "currency": getattr(item, "currency", None),
    }


def _rule_brief(item: Promotion) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "discount_type": item.discount_type,
        "discount_value": item.discount_value,
        "max_discount_amount": item.max_discount_amount,
        "minimum_subtotal": item.minimum_subtotal,
        "currency": item.currency,
        "valid_from": item.valid_from,
        "valid_until": item.valid_until,
        "stay_date_start": item.stay_date_start,
        "stay_date_end": item.stay_date_end,
        "total_usage_limit": item.total_usage_limit,
        "per_customer_limit": item.per_customer_limit,
        "active": item.active,
        "eligibility": {
            "property_ids": item.property_ids,
            "room_type_ids": item.room_type_ids,
            "rate_plan_ids": item.rate_plan_ids,
            "sources": item.sources,
        },
    }


def _code_brief(
    code: PromotionCode, promotion: Promotion, confirmed, counted, rule_counted
):
    # Mirrors PromotionService._reason: the code limit counts this code, the
    # rule total counts every code of the rule; the tighter one wins.
    headroom = [
        limit - used
        for limit, used in (
            (code.usage_limit, int(counted)),
            (promotion.total_usage_limit, int(rule_counted)),
        )
        if limit is not None
    ]
    limits = [
        value
        for value in (code.usage_limit, promotion.total_usage_limit)
        if value is not None
    ]
    limit = min(limits) if limits else None
    return {
        "id": code.id,
        "code": code.code,
        "status": code.status,
        "promotion_id": promotion.id,
        "usage_limit": code.usage_limit,
        "effective_limit": limit,
        "confirmed_uses": int(confirmed),
        "counted_uses": int(counted),
        "rule_uses": int(rule_counted),
        "remaining": max(min(headroom), 0) if headroom else None,
        "discount": {
            "type": promotion.discount_type,
            "value": promotion.discount_value,
            "currency": promotion.currency,
        },
        "updated_at": code.updated_at,
    }


__all__ = [
    "FUNDING",
    "PlatformCampaignActivationError",
    "PlatformCampaignError",
    "PlatformCampaignService",
    "PlatformRangeError",
    "validate_range",
]
