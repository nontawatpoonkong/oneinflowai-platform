"""Cross-tenant, read-mostly platform operations behind a dedicated authority."""

import math
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError
from app.models.ai_tool import AIToolAction, AIToolActionStatus
from app.models.audit import (
    AuditActorType,
    AuditArea,
    ProductUsageEvent,
    WorkspaceAuditEvent,
)
from app.models.automation import (
    AutomationExecution,
    AutomationExecutionStatus,
    AutomationWorkerHeartbeat,
    DomainEventOutbox,
)
from app.models.billing import (
    BillingAccount,
    PlanEntitlement,
    SaaSPlan,
    SubscriptionStatus,
    SubscriptionWorkspaceAllocation,
    WorkspaceSubscription,
)
from app.models.booking import Booking, BookingStatus
from app.models.channel import ChannelConnection, ChannelMessageDelivery
from app.models.conversation import Conversation
from app.models.hotel import Property, RoomType
from app.models.payment import Payment, PaymentApplicationStatus
from app.models.pms import PMSConnection
from app.models.promotion import (
    BookingAttribution,
    PromotionCampaign,
    PromotionCampaignStatus,
    PromotionCode,
    PromotionCodeStatus,
)
from app.models.stay import HotelRoom, Stay
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceStatus
from app.models.workspace_member import WorkspaceMember
from app.services.audit import AuditService
from app.services.platform_campaign import PlatformCampaignService
from app.services.promotion_lifecycle import PromotionLifecycleService


class PlatformOperationError(AppError):
    status_code = 409
    code = "PLATFORM_OPERATION_INVALID"
    message = "Platform operation is not allowed"


class PlatformAdminService:
    """All cross-Workspace queries live here; Workspace dependencies are not reused."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _page(items: list[dict], total: int, page: int, page_size: int) -> dict:
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if total else 0,
        }

    async def users(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        verified: bool | None,
        active: bool | None,
        has_workspace: bool | None,
        has_subscription: bool | None,
        platform_admin: bool | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> dict:
        owned = (
            select(func.count(Workspace.id))
            .where(Workspace.owner_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        memberships = (
            select(func.count(WorkspaceMember.id))
            .where(WorkspaceMember.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        subscriptions = (
            select(func.count(WorkspaceSubscription.id))
            .join(
                BillingAccount,
                BillingAccount.id == WorkspaceSubscription.billing_account_id,
            )
            .where(BillingAccount.owner_user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        last_activity = (
            select(func.max(ProductUsageEvent.occurred_at))
            .where(ProductUsageEvent.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        filters = []
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(User.email.ilike(term), User.full_name.ilike(term)))
        if verified is not None:
            filters.append(User.email_verified.is_(verified))
        if active is not None:
            filters.append(User.is_active.is_(active))
        if platform_admin is not None:
            filters.append(User.is_platform_admin.is_(platform_admin))
        if has_workspace is not None:
            filters.append((memberships > 0) if has_workspace else (memberships == 0))
        if has_subscription is not None:
            filters.append(
                (subscriptions > 0) if has_subscription else (subscriptions == 0)
            )
        if created_from:
            filters.append(User.created_at >= created_from)
        if created_to:
            filters.append(User.created_at < created_to)
        total = int(
            await self.session.scalar(select(func.count(User.id)).where(*filters)) or 0
        )
        rows = (
            await self.session.execute(
                select(
                    User,
                    owned.label("owned"),
                    memberships.label("memberships"),
                    subscriptions.label("subscriptions"),
                    last_activity.label("last_activity"),
                )
                .where(*filters)
                .order_by(User.created_at.desc(), User.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = [
            {
                "id": user.id,
                "name": user.full_name,
                "email": user.email,
                "verified": user.email_verified,
                "status": "ACTIVE" if user.is_active else "SUSPENDED",
                "platform_admin": user.is_platform_admin,
                "has_billing_account": bool(subscription_count),
                "owned_workspaces": int(owned_count),
                "membership_count": int(membership_count),
                "subscription_count": int(subscription_count),
                "created_at": user.created_at,
                "last_product_activity_at": activity,
            }
            for (
                user,
                owned_count,
                membership_count,
                subscription_count,
                activity,
            ) in rows
        ]
        return self._page(items, total, page, page_size)

    async def user_detail(self, user_id: uuid.UUID) -> dict:
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")
        account = await self.session.scalar(
            select(BillingAccount).where(BillingAccount.owner_user_id == user.id)
        )
        owned = list(
            await self.session.scalars(
                select(Workspace)
                .where(Workspace.owner_id == user.id)
                .order_by(Workspace.created_at)
                .limit(100)
            )
        )
        memberships = (
            await self.session.execute(
                select(WorkspaceMember, Workspace)
                .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(WorkspaceMember.created_at)
                .limit(100)
            )
        ).all()
        recent_usage = list(
            await self.session.scalars(
                select(ProductUsageEvent)
                .where(ProductUsageEvent.user_id == user.id)
                .order_by(ProductUsageEvent.occurred_at.desc())
                .limit(20)
            )
        )
        audits = list(
            await self.session.scalars(
                select(WorkspaceAuditEvent)
                .where(WorkspaceAuditEvent.actor_user_id == user.id)
                .order_by(WorkspaceAuditEvent.occurred_at.desc())
                .limit(20)
            )
        )
        return {
            "profile": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "verified": user.email_verified,
                "verified_at": user.email_verified_at,
                "status": "ACTIVE" if user.is_active else "SUSPENDED",
                "platform_admin": user.is_platform_admin,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
            },
            "billing": (
                {
                    "id": account.id,
                    "status": account.status,
                    "created_at": account.created_at,
                }
                if account
                else None
            ),
            "owned_workspaces": [self._workspace_brief(item) for item in owned],
            "memberships": [
                {
                    "workspace": self._workspace_brief(workspace),
                    "role": member.role,
                    "joined_at": member.created_at,
                }
                for member, workspace in memberships
            ],
            "recent_usage": [
                {
                    "feature": item.feature,
                    "page_path": item.page_path,
                    "occurred_at": item.occurred_at,
                }
                for item in recent_usage
            ],
            "recent_audit": [self._audit_brief(item) for item in audits],
        }

    async def set_user_active(
        self, *, actor: User, user_id: uuid.UUID, active: bool, reason: str
    ) -> User:
        user = await self.session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None:
            raise NotFoundError("User not found")
        if actor.id == user.id and not active:
            raise PlatformOperationError(
                "Platform administrators cannot suspend themselves"
            )
        if user.is_active == active:
            return user
        user.is_active = active
        if not active:
            # Tokens issued before the suspension stay revoked after a later
            # reactivation; the user signs in again.
            user.token_version += 1
        AuditService(self.session).record(
            workspace_id=None,
            actor_user_id=actor.id,
            actor_type=AuditActorType.PLATFORM_ADMIN,
            action=(
                "PLATFORM_USER_REACTIVATED" if active else "PLATFORM_USER_SUSPENDED"
            ),
            area=AuditArea.SETTINGS,
            resource_type="User",
            resource_id=user.id,
            metadata={
                "reason": reason,
                "new_status": "ACTIVE" if active else "SUSPENDED",
            },
        )
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def workspaces(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None,
        status: str | None,
        subscription_status: str | None,
        pms_connected: bool | None,
        recently_active: bool | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> dict:
        filters = []
        if search:
            filters.append(Workspace.name.ilike(f"%{search.strip()}%"))
        if status:
            filters.append(Workspace.status == status)
        if created_from:
            filters.append(Workspace.created_at >= created_from)
        if created_to:
            filters.append(Workspace.created_at < created_to)
        if subscription_status:
            filters.append(
                WorkspaceSubscription.status == SubscriptionStatus(subscription_status)
            )
        if pms_connected is not None:
            exists_pms = (
                select(PMSConnection.id)
                .where(
                    PMSConnection.workspace_id == Workspace.id,
                    PMSConnection.status == "CONNECTED",
                )
                .exists()
            )
            filters.append(exists_pms if pms_connected else ~exists_pms)
        if recently_active is not None:
            cutoff = datetime.now(UTC) - timedelta(days=30)
            exists_usage = (
                select(ProductUsageEvent.id)
                .where(
                    ProductUsageEvent.workspace_id == Workspace.id,
                    ProductUsageEvent.occurred_at >= cutoff,
                )
                .exists()
            )
            filters.append(exists_usage if recently_active else ~exists_usage)
        member_count = (
            select(func.count(WorkspaceMember.id))
            .where(WorkspaceMember.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        property_count = (
            select(func.count(Property.id))
            .where(Property.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        last_usage = (
            select(func.max(ProductUsageEvent.occurred_at))
            .where(ProductUsageEvent.workspace_id == Workspace.id)
            .correlate(Workspace)
            .scalar_subquery()
        )
        pms_status = (
            select(PMSConnection.status)
            .where(PMSConnection.workspace_id == Workspace.id)
            .order_by(PMSConnection.updated_at.desc())
            .limit(1)
            .correlate(Workspace)
            .scalar_subquery()
        )
        stmt = (
            select(
                Workspace,
                User.email,
                member_count.label("members"),
                property_count.label("properties"),
                last_usage.label("last_usage"),
                pms_status.label("pms_status"),
                WorkspaceSubscription.status.label("subscription_status"),
                SaaSPlan.display_name.label("plan_name"),
            )
            .join(User, User.id == Workspace.owner_id)
            .outerjoin(
                WorkspaceSubscription,
                WorkspaceSubscription.workspace_id == Workspace.id,
            )
            .outerjoin(SaaSPlan, SaaSPlan.id == WorkspaceSubscription.plan_id)
            .where(*filters)
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                stmt.order_by(Workspace.created_at.desc(), Workspace.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = [
            {
                "id": workspace.id,
                "name": workspace.name,
                "slug": workspace.slug,
                "status": workspace.status,
                "owner": {"id": workspace.owner_id, "email": owner_email},
                "plan": plan_name,
                "subscription_status": sub_status,
                "members": int(members),
                "properties": int(properties),
                "created_at": workspace.created_at,
                "last_usage_at": usage,
                "pms_status": pms,
            }
            for (
                workspace,
                owner_email,
                members,
                properties,
                usage,
                pms,
                sub_status,
                plan_name,
            ) in rows
        ]
        return self._page(items, total, page, page_size)

    async def workspace_detail(self, workspace_id: uuid.UUID) -> dict:
        workspace = await self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise NotFoundError("Workspace not found")
        owner = await self.session.get(User, workspace.owner_id)
        counts = {
            "members": await self._count(
                WorkspaceMember, WorkspaceMember.workspace_id == workspace.id
            ),
            "properties": await self._count(
                Property, Property.workspace_id == workspace.id
            ),
            "room_types": await self._count(
                RoomType, RoomType.workspace_id == workspace.id
            ),
            "rooms": await self._count(
                HotelRoom, HotelRoom.workspace_id == workspace.id
            ),
            "bookings": await self._count(
                Booking, Booking.workspace_id == workspace.id
            ),
            "stays": await self._count(Stay, Stay.workspace_id == workspace.id),
        }
        subscription = await self.session.scalar(
            select(WorkspaceSubscription)
            .where(WorkspaceSubscription.workspace_id == workspace.id)
            .order_by(WorkspaceSubscription.created_at.desc())
        )
        pms = list(
            await self.session.scalars(
                select(PMSConnection)
                .where(PMSConnection.workspace_id == workspace.id)
                .order_by(PMSConnection.created_at.desc())
                .limit(20)
            )
        )
        automation_counts = dict(
            (
                await self.session.execute(
                    select(AutomationExecution.status, func.count())
                    .where(AutomationExecution.workspace_id == workspace.id)
                    .group_by(AutomationExecution.status)
                )
            ).all()
        )
        recent_audit = list(
            await self.session.scalars(
                select(WorkspaceAuditEvent)
                .where(WorkspaceAuditEvent.workspace_id == workspace.id)
                .order_by(WorkspaceAuditEvent.occurred_at.desc())
                .limit(20)
            )
        )
        return {
            "workspace": self._workspace_brief(workspace),
            "owner": {"id": owner.id, "email": owner.email, "name": owner.full_name}
            if owner
            else None,
            "counts": counts,
            "subscription": self._subscription_brief(subscription)
            if subscription
            else None,
            "pms": [self._pms_brief(item) for item in pms],
            "automation": {
                str(key): int(value) for key, value in automation_counts.items()
            },
            "recent_audit": [self._audit_brief(item) for item in recent_audit],
        }

    async def set_workspace_status(
        self,
        *,
        actor: User,
        workspace_id: uuid.UUID,
        status: WorkspaceStatus,
        reason: str,
    ) -> Workspace:
        workspace = await self.session.scalar(
            select(Workspace).where(Workspace.id == workspace_id).with_for_update()
        )
        if workspace is None:
            raise NotFoundError("Workspace not found")
        if workspace.status == status.value:
            return workspace
        previous = workspace.status
        workspace.status = status.value
        AuditService(self.session).record(
            workspace_id=workspace.id,
            actor_user_id=actor.id,
            actor_type=AuditActorType.PLATFORM_ADMIN,
            action=(
                "PLATFORM_WORKSPACE_REACTIVATED"
                if status is WorkspaceStatus.ACTIVE
                else "PLATFORM_WORKSPACE_SUSPENDED"
            ),
            area=AuditArea.WORKSPACE,
            resource_type="Workspace",
            resource_id=workspace.id,
            metadata={
                "reason": reason,
                "previous_status": previous,
                "new_status": status.value,
            },
        )
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def subscriptions(
        self, *, page: int, page_size: int, status: str | None, search: str | None
    ) -> dict:
        filters = []
        if status:
            filters.append(WorkspaceSubscription.status == SubscriptionStatus(status))
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    User.email.ilike(term),
                    SaaSPlan.display_name.ilike(term),
                    cast(WorkspaceSubscription.id, String).ilike(term),
                )
            )
        allocation_count = (
            select(func.count(SubscriptionWorkspaceAllocation.id))
            .where(
                SubscriptionWorkspaceAllocation.subscription_id
                == WorkspaceSubscription.id
            )
            .correlate(WorkspaceSubscription)
            .scalar_subquery()
        )
        stmt = (
            select(
                WorkspaceSubscription,
                BillingAccount,
                User,
                SaaSPlan,
                allocation_count.label("allocations"),
            )
            .join(
                BillingAccount,
                BillingAccount.id == WorkspaceSubscription.billing_account_id,
            )
            .join(User, User.id == BillingAccount.owner_user_id)
            .join(SaaSPlan, SaaSPlan.id == WorkspaceSubscription.plan_id)
            .where(*filters)
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                stmt.order_by(WorkspaceSubscription.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = [
            {
                **self._subscription_brief(subscription),
                "billing_account": {"id": account.id, "status": account.status},
                "owner": {
                    "id": owner.id,
                    "email": owner.email,
                    "name": owner.full_name,
                },
                "plan": {"id": plan.id, "key": plan.key, "name": plan.display_name},
                "allocated_workspaces": int(allocations),
            }
            for subscription, account, owner, plan, allocations in rows
        ]
        return self._page(items, total, page, page_size)

    async def plans(self, *, page: int, page_size: int) -> dict:
        total = await self._count(SaaSPlan)
        plans = list(
            await self.session.scalars(
                select(SaaSPlan)
                .order_by(SaaSPlan.created_at, SaaSPlan.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        items = []
        for plan in plans:
            entitlements = list(
                await self.session.scalars(
                    select(PlanEntitlement)
                    .where(PlanEntitlement.plan_id == plan.id)
                    .order_by(PlanEntitlement.key)
                )
            )
            items.append(
                {
                    "id": plan.id,
                    "key": plan.key,
                    "display_name": plan.display_name,
                    "is_active": plan.is_active,
                    "billing_interval": plan.billing_interval,
                    "price_minor": plan.price_minor,
                    "currency": plan.currency,
                    "pricing_note": plan.pricing_note,
                    "authority": "CODE_SEEDED_READ_ONLY",
                    "entitlements": [
                        {
                            "key": item.key,
                            "kind": item.kind,
                            "enabled": item.enabled,
                            "limit": item.limit_value,
                            "overage_allowed": item.overage_allowed,
                        }
                        for item in entitlements
                    ],
                }
            )
        return self._page(items, total, page, page_size)

    async def campaigns(
        self,
        *,
        page: int,
        page_size: int,
        workspace_id: uuid.UUID | None,
        status: str | None,
    ) -> dict:
        return await PlatformCampaignService(self.session).list_campaigns(
            page=page,
            page_size=page_size,
            workspace_id=workspace_id,
            status=PromotionCampaignStatus(status) if status else None,
        )

    async def set_campaign_status(
        self,
        *,
        actor: User,
        campaign_id: uuid.UUID,
        status: PromotionCampaignStatus,
        reason: str,
    ) -> PromotionCampaign:
        """Delegate to the single promotion lifecycle authority."""

        return await PlatformCampaignService(self.session).transition_campaign(
            actor, campaign_id, status, reason
        )

    async def codes(
        self,
        *,
        page: int,
        page_size: int,
        workspace_id: uuid.UUID | None,
        status: str | None,
    ) -> dict:
        return await PlatformCampaignService(self.session).list_codes(
            page=page,
            page_size=page_size,
            workspace_id=workspace_id,
            status=PromotionCodeStatus(status) if status else None,
        )

    async def set_code_status(
        self,
        *,
        actor: User,
        code_id: uuid.UUID,
        status: PromotionCodeStatus,
        reason: str,
    ) -> PromotionCode:
        return await PlatformCampaignService(self.session).transition_code(
            actor, code_id, status, reason
        )

    async def attribution(self, *, page: int, page_size: int) -> dict:
        """Aggregate hotel marketing value without claiming campaign ROI."""

        grouped = (
            select(
                BookingAttribution.workspace_id,
                Workspace.name.label("workspace_name"),
                BookingAttribution.campaign_id,
                PromotionCampaign.name.label("campaign_name"),
                BookingAttribution.promotion_code_id,
                PromotionCode.code.label("code"),
                BookingAttribution.source,
                Booking.currency,
                func.count(Booking.id).label("bookings"),
                func.sum(
                    case((Booking.status == BookingStatus.CONFIRMED, 1), else_=0)
                ).label("confirmed_bookings"),
                func.coalesce(func.sum(Booking.subtotal), 0).label("gross_value"),
                func.coalesce(func.sum(Booking.discount_amount), 0).label("discount"),
                func.coalesce(func.sum(Booking.total_amount), 0).label("net_value"),
            )
            .join(Workspace, Workspace.id == BookingAttribution.workspace_id)
            .join(Booking, Booking.id == BookingAttribution.booking_id)
            .outerjoin(
                PromotionCampaign,
                PromotionCampaign.id == BookingAttribution.campaign_id,
            )
            .outerjoin(
                PromotionCode,
                PromotionCode.id == BookingAttribution.promotion_code_id,
            )
            .group_by(
                BookingAttribution.workspace_id,
                Workspace.name,
                BookingAttribution.campaign_id,
                PromotionCampaign.name,
                BookingAttribution.promotion_code_id,
                PromotionCode.code,
                BookingAttribution.source,
                Booking.currency,
            )
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(grouped.subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                grouped.order_by(Workspace.name, Booking.currency)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return self._page([dict(row._mapping) for row in rows], total, page, page_size)

    async def analytics(self) -> dict:
        now = datetime.now(UTC)
        user_counts = {
            "registered": await self._count(User),
            "verified": await self._count(User, User.email_verified.is_(True)),
            "billing_accounts": await self._count(BillingAccount),
            "subscriptions": await self._count(WorkspaceSubscription),
            "activated_subscriptions": await self._count(
                WorkspaceSubscription,
                WorkspaceSubscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
                ),
            ),
            "workspaces": await self._count(Workspace),
        }

        async def active_users(days: int) -> int:
            return int(
                await self.session.scalar(
                    select(func.count(func.distinct(ProductUsageEvent.user_id))).where(
                        ProductUsageEvent.user_id.is_not(None),
                        ProductUsageEvent.occurred_at >= now - timedelta(days=days),
                        ProductUsageEvent.occurred_at < now,
                    )
                )
                or 0
            )

        feature_rows = (
            await self.session.execute(
                select(ProductUsageEvent.feature, func.count())
                .where(ProductUsageEvent.feature.is_not(None))
                .group_by(ProductUsageEvent.feature)
                .order_by(func.count().desc())
            )
        ).all()
        booking_value = (
            await self.session.execute(
                select(
                    Booking.currency,
                    func.count(),
                    func.coalesce(func.sum(Booking.total_amount), 0),
                )
                .where(Booking.status == BookingStatus.CONFIRMED)
                .group_by(Booking.currency)
                .order_by(Booking.currency)
            )
        ).all()
        return {
            "saas_funnel": user_counts,
            "active_users": {
                "dau": await active_users(1),
                "wau": await active_users(7),
                "mau": await active_users(30),
                "definition": (
                    "Unique authenticated users with accepted PAGE_VIEW events "
                    "in rolling UTC windows of 1, 7, and 30 days."
                ),
                "timezone": "UTC",
            },
            "product_usage": [
                {"feature": feature, "page_views": int(count)}
                for feature, count in feature_rows
            ],
            "hotel_network": {
                "workspaces": await self._count(Workspace),
                "properties": await self._count(Property),
                "room_types": await self._count(RoomType),
                "physical_rooms": await self._count(HotelRoom),
                "bookings": await self._count(Booking),
                "stays": await self._count(Stay),
                "pms_connections": await self._count(PMSConnection),
            },
            "hotel_booking_value": [
                {"currency": currency, "confirmed_bookings": int(count), "value": value}
                for currency, count, value in booking_value
            ],
            "saas_revenue": {
                "available": False,
                "reason": (
                    "No authoritative subscription payment ledger exists; "
                    "manual activation is not revenue."
                ),
            },
        }

    async def operations(self) -> dict:
        now = datetime.now(UTC)
        worker_cutoff = now - timedelta(minutes=2)
        worker_rows = list(
            await self.session.scalars(
                select(AutomationWorkerHeartbeat)
                .order_by(AutomationWorkerHeartbeat.last_heartbeat_at.desc())
                .limit(100)
            )
        )
        automation = dict(
            (
                await self.session.execute(
                    select(AutomationExecution.status, func.count()).group_by(
                        AutomationExecution.status
                    )
                )
            ).all()
        )
        ai = dict(
            (
                await self.session.execute(
                    select(AIToolAction.status, func.count()).group_by(
                        AIToolAction.status
                    )
                )
            ).all()
        )
        pms = list(
            await self.session.scalars(
                select(PMSConnection)
                .order_by(PMSConnection.updated_at.desc())
                .limit(100)
            )
        )
        channels = list(
            await self.session.scalars(
                select(ChannelConnection)
                .order_by(ChannelConnection.updated_at.desc())
                .limit(100)
            )
        )
        return {
            "ai": {
                "conversations": await self._count(Conversation),
                "tool_actions": {str(key): int(value) for key, value in ai.items()},
                "hidden_reasoning_exposed": False,
            },
            "automation": {
                "executions": {
                    str(key): int(value) for key, value in automation.items()
                },
                "terminal_failures": await self._count(
                    AutomationExecution, AutomationExecution.terminal_failure.is_(True)
                ),
                "oldest_pending": await self.session.scalar(
                    select(func.min(AutomationExecution.scheduled_for)).where(
                        AutomationExecution.status
                        == AutomationExecutionStatus.PENDING.value
                    )
                ),
                "workers": [
                    {
                        "worker_id": item.worker_id,
                        "state": item.state,
                        "last_heartbeat_at": item.last_heartbeat_at,
                        "stale": item.last_heartbeat_at < worker_cutoff,
                    }
                    for item in worker_rows
                ],
            },
            "pms": [self._pms_brief(item) for item in pms],
            "channels": [
                {
                    "id": item.id,
                    "workspace_id": item.workspace_id,
                    "provider": item.provider,
                    "display_name": item.display_name,
                    "status": item.status,
                    "last_verified_at": item.last_verified_at,
                    "last_error_code": item.last_error_code,
                }
                for item in channels
            ],
            "channel_delivery_failures": await self._count(
                ChannelMessageDelivery,
                ChannelMessageDelivery.last_error_code.is_not(None),
            ),
        }

    async def overview(self) -> dict:
        analytics = await self.analytics()
        operations = await self.operations()
        subscription_rows = dict(
            (
                await self.session.execute(
                    select(WorkspaceSubscription.status, func.count()).group_by(
                        WorkspaceSubscription.status
                    )
                )
            ).all()
        )
        booking_rows = (
            await self.session.execute(
                select(
                    Booking.currency, func.coalesce(func.sum(Booking.total_amount), 0)
                )
                .where(Booking.status == BookingStatus.CONFIRMED)
                .group_by(Booking.currency)
            )
        ).all()
        attention = {
            "pending_subscription_activations": int(
                subscription_rows.get(SubscriptionStatus.PENDING_ACTIVATION, 0)
            ),
            "terminal_automation_failures": operations["automation"][
                "terminal_failures"
            ],
            "stale_automation_workers": sum(
                1 for item in operations["automation"]["workers"] if item["stale"]
            ),
            "pms_failures": sum(
                1 for item in operations["pms"] if item["status"] == "ERROR"
            ),
            "payment_reviews": await self._count(
                Payment,
                Payment.booking_application_status
                == PaymentApplicationStatus.REQUIRES_REVIEW,
            ),
            "ai_tool_failures": int(
                operations["ai"]["tool_actions"].get(AIToolActionStatus.FAILED.value, 0)
            ),
            "channel_failures": operations["channel_delivery_failures"],
        }
        return {
            "metrics": {
                "total_users": analytics["saas_funnel"]["registered"],
                "verified_users": analytics["saas_funnel"]["verified"],
                "active_users_30d": analytics["active_users"]["mau"],
                "total_workspaces": analytics["hotel_network"]["workspaces"],
                "active_workspaces": await self._count(
                    Workspace, Workspace.status == WorkspaceStatus.ACTIVE.value
                ),
                "subscriptions": {
                    str(key.value if hasattr(key, "value") else key): int(value)
                    for key, value in subscription_rows.items()
                },
                "confirmed_bookings": await self._count(
                    Booking, Booking.status == BookingStatus.CONFIRMED
                ),
                "hotel_booking_value": [
                    {"currency": currency, "value": value}
                    for currency, value in booking_rows
                ],
                "ai_conversations": operations["ai"]["conversations"],
                "ai_tool_executions": sum(operations["ai"]["tool_actions"].values()),
                "automation_executions": sum(
                    operations["automation"]["executions"].values()
                ),
                "pms_connections": len(operations["pms"]),
            },
            "needs_attention": attention,
            "links": {
                "pending_subscriptions": (
                    "/platform/subscriptions?status=PENDING_ACTIVATION"
                ),
                "automation_failures": (
                    "/platform/operations?section=automation&status=FAILED"
                ),
                "pms_failures": "/platform/operations?section=pms&status=ERROR",
                "audit": "/platform/audit?result=FAILED",
            },
        }

    async def global_audit(
        self,
        *,
        page: int,
        page_size: int,
        workspace_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        actor_type: str | None,
        area: str | None,
        action: str | None,
        result: str | None,
        resource_type: str | None,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> dict:
        filters = []
        for value, column in (
            (workspace_id, WorkspaceAuditEvent.workspace_id),
            (actor_user_id, WorkspaceAuditEvent.actor_user_id),
            (actor_type, WorkspaceAuditEvent.actor_type),
            (area, WorkspaceAuditEvent.area),
            (action, WorkspaceAuditEvent.action),
            (result, WorkspaceAuditEvent.result),
            (resource_type, WorkspaceAuditEvent.resource_type),
        ):
            if value is not None:
                filters.append(column == value)
        if start_at:
            filters.append(WorkspaceAuditEvent.occurred_at >= start_at)
        if end_at:
            filters.append(WorkspaceAuditEvent.occurred_at < end_at)
        total = await self._count(WorkspaceAuditEvent, *filters)
        rows = (
            await self.session.execute(
                select(WorkspaceAuditEvent, User, Workspace.name)
                .outerjoin(User, User.id == WorkspaceAuditEvent.actor_user_id)
                .outerjoin(Workspace, Workspace.id == WorkspaceAuditEvent.workspace_id)
                .where(*filters)
                .order_by(
                    WorkspaceAuditEvent.occurred_at.desc(),
                    WorkspaceAuditEvent.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return self._page(
            [
                {
                    **self._audit_brief(event),
                    "workspace": (
                        {"id": event.workspace_id, "name": workspace_name}
                        if event.workspace_id
                        else None
                    ),
                    "actor": (
                        {"id": user.id, "email": user.email, "name": user.full_name}
                        if user
                        else {"id": None, "email": None, "name": event.actor_type}
                    ),
                }
                for event, user, workspace_name in rows
            ],
            total,
            page,
            page_size,
        )

    async def system_health(self) -> dict:
        await self.session.scalar(select(1))
        now = datetime.now(UTC)
        last_worker = await self.session.scalar(
            select(func.max(AutomationWorkerHeartbeat.last_heartbeat_at))
        )
        queue = dict(
            (
                await self.session.execute(
                    select(DomainEventOutbox.state, func.count()).group_by(
                        DomainEventOutbox.state
                    )
                )
            ).all()
        )
        return {
            "database": "HEALTHY",
            "automation_workers": {
                "last_heartbeat_at": last_worker,
                "status": "HEALTHY"
                if last_worker and last_worker >= now - timedelta(minutes=2)
                else "NO_RECENT_HEARTBEAT",
            },
            "queue": {str(key): int(value) for key, value in queue.items()},
            "promotion_lifecycle": await PromotionLifecycleService(
                self.session
            ).status(
                stale_after_seconds=get_settings().PROMOTION_LIFECYCLE_STALE_SECONDS
            ),
            "generated_at": now,
            "secrets_exposed": False,
            "configuration_editable": False,
        }

    async def _count(self, model, *filters) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(model).where(*filters)
            )
            or 0
        )

    @staticmethod
    def _workspace_brief(item: Workspace) -> dict:
        return {
            "id": item.id,
            "name": item.name,
            "slug": item.slug,
            "owner_id": item.owner_id,
            "status": item.status,
            "created_at": item.created_at,
        }

    @staticmethod
    def _subscription_brief(item: WorkspaceSubscription) -> dict:
        return {
            "id": item.id,
            "workspace_id": item.workspace_id,
            "status": item.status,
            "period_start": item.current_period_start,
            "period_end": item.current_period_end,
            "trial_end": item.trial_end,
            "cancel_at_period_end": item.cancel_at_period_end,
            "provider": item.provider,
            "created_at": item.created_at,
        }

    @staticmethod
    def _pms_brief(item: PMSConnection) -> dict:
        return {
            "id": item.id,
            "workspace_id": item.workspace_id,
            "provider": item.provider,
            "name": item.name,
            "status": item.status,
            "sync_mode": item.sync_mode,
            "inventory_authority": item.inventory_authority,
            "last_successful_sync_at": item.last_successful_sync_at,
            "last_failed_sync_at": item.last_failed_sync_at,
            "last_error_code": item.last_error_code,
        }

    @staticmethod
    def _audit_brief(item: WorkspaceAuditEvent) -> dict:
        return {
            "id": item.id,
            "workspace_id": item.workspace_id,
            "actor_user_id": item.actor_user_id,
            "actor_type": item.actor_type,
            "action": item.action,
            "area": item.area,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "result": item.result,
            "safe_metadata": item.safe_metadata,
            "occurred_at": item.occurred_at,
        }
