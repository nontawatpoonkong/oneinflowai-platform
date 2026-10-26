"""Account-owned billing and atomic Workspace provisioning."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BillingAccountAccessDeniedError,
    InvalidSubscriptionTransitionError,
    PlatformAdminRequiredError,
    SubscriptionAllocationExhaustedError,
    SubscriptionNotEligibleError,
    SubscriptionNotFoundError,
)
from app.models.audit import AuditActorType, AuditArea
from app.models.billing import (
    BillingAccount,
    BillingAccountStatus,
    BillingAuditEvent,
    SaaSPlan,
    SubscriptionStatus,
    SubscriptionWorkspaceAllocation,
    WorkspaceSubscription,
)
from app.models.user import User
from app.services.audit import AuditService

ELIGIBLE_PROVISIONING_STATUSES = {
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.TRIALING,
}


class AccountBillingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_account(self, owner_user_id: uuid.UUID) -> BillingAccount | None:
        return await self.session.scalar(
            select(BillingAccount).where(BillingAccount.owner_user_id == owner_user_id)
        )

    async def get_or_create_account(self, owner_user_id: uuid.UUID) -> BillingAccount:
        account = await self.get_account(owner_user_id)
        if account is not None:
            return account
        account = BillingAccount(
            owner_user_id=owner_user_id,
            status=BillingAccountStatus.ACTIVE,
        )
        self.session.add(account)
        await self.session.flush()
        self._audit(
            account=account,
            actor_user_id=owner_user_id,
            action="BILLING_ACCOUNT_CREATED",
        )
        return account

    async def list_subscriptions(
        self, owner_user_id: uuid.UUID
    ) -> list[WorkspaceSubscription]:
        account = await self.get_account(owner_user_id)
        if account is None:
            return []
        return list(
            await self.session.scalars(
                select(WorkspaceSubscription)
                .where(WorkspaceSubscription.billing_account_id == account.id)
                .order_by(WorkspaceSubscription.created_at.desc())
            )
        )

    async def create_pending_subscription(
        self, *, owner_user_id: uuid.UUID, plan_id: uuid.UUID
    ) -> WorkspaceSubscription:
        plan = await self.session.get(SaaSPlan, plan_id)
        if plan is None or not plan.is_active:
            raise SubscriptionNotFoundError("Active plan not found")
        account = await self.get_or_create_account(owner_user_id)
        existing = await self.session.scalar(
            select(WorkspaceSubscription)
            .where(
                WorkspaceSubscription.billing_account_id == account.id,
                WorkspaceSubscription.plan_id == plan.id,
                WorkspaceSubscription.status == SubscriptionStatus.PENDING_ACTIVATION,
            )
            .order_by(WorkspaceSubscription.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        now = datetime.now(UTC)
        subscription = WorkspaceSubscription(
            billing_account_id=account.id,
            workspace_id=None,
            plan_id=plan.id,
            status=SubscriptionStatus.PENDING_ACTIVATION,
            billing_interval=plan.billing_interval,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            provider="manual_pilot",
            workspace_limit=1,
        )
        self.session.add(subscription)
        await self.session.flush()
        self._audit(
            account=account,
            subscription=subscription,
            actor_user_id=owner_user_id,
            action="SUBSCRIPTION_CREATED",
            new_status=subscription.status.value,
        )
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def activate_subscription(
        self,
        *,
        actor: User,
        subscription_id: uuid.UUID,
        target_status: SubscriptionStatus,
        reason: str | None,
    ) -> WorkspaceSubscription:
        if not actor.is_platform_admin:
            raise PlatformAdminRequiredError()
        if target_status not in ELIGIBLE_PROVISIONING_STATUSES:
            raise InvalidSubscriptionTransitionError()
        subscription = await self.session.scalar(
            select(WorkspaceSubscription)
            .where(WorkspaceSubscription.id == subscription_id)
            .with_for_update()
        )
        if subscription is None:
            raise SubscriptionNotFoundError()
        if subscription.status == target_status:
            return subscription
        if subscription.status != SubscriptionStatus.PENDING_ACTIVATION:
            raise InvalidSubscriptionTransitionError()

        old_status = subscription.status.value
        now = datetime.now(UTC)
        subscription.status = target_status
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=30)
        subscription.trial_end = (
            subscription.current_period_end
            if target_status == SubscriptionStatus.TRIALING
            else None
        )
        account = await self.session.get(
            BillingAccount, subscription.billing_account_id
        )
        self._audit(
            account=account,
            subscription=subscription,
            actor_user_id=actor.id,
            action="SUBSCRIPTION_ACTIVATED",
            old_status=old_status,
            new_status=target_status.value,
            reason=reason,
        )
        AuditService(self.session).record(
            workspace_id=subscription.workspace_id,
            actor_user_id=actor.id,
            actor_type=AuditActorType.PLATFORM_ADMIN,
            action="PLATFORM_SUBSCRIPTION_ACTIVATED",
            area=AuditArea.BILLING,
            resource_type="WorkspaceSubscription",
            resource_id=subscription.id,
            metadata={
                "previous_status": old_status,
                "new_status": target_status.value,
                "reason_provided": bool(reason),
            },
        )
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def provision_workspace(
        self,
        *,
        owner_user_id: uuid.UUID,
        subscription_id: uuid.UUID,
        name: str,
    ):
        from app.services.workspace import WorkspaceService

        subscription = await self.session.scalar(
            select(WorkspaceSubscription)
            .where(WorkspaceSubscription.id == subscription_id)
            .with_for_update()
        )
        if subscription is None:
            raise SubscriptionNotFoundError()
        account = await self.session.get(
            BillingAccount, subscription.billing_account_id
        )
        if account is None or account.owner_user_id != owner_user_id:
            raise BillingAccountAccessDeniedError()
        now = datetime.now(UTC)
        if (
            account.status != BillingAccountStatus.ACTIVE
            or subscription.status not in ELIGIBLE_PROVISIONING_STATUSES
            or subscription.current_period_end <= now
        ):
            raise SubscriptionNotEligibleError()

        allocation_count = await self.session.scalar(
            select(func.count(SubscriptionWorkspaceAllocation.id)).where(
                SubscriptionWorkspaceAllocation.subscription_id == subscription.id
            )
        )
        if (allocation_count or 0) >= subscription.workspace_limit:
            raise SubscriptionAllocationExhaustedError()

        workspace = await WorkspaceService(self.session).build_with_owner(
            owner_id=owner_user_id, name=name
        )
        allocation = SubscriptionWorkspaceAllocation(
            subscription_id=subscription.id,
            workspace_id=workspace.id,
            allocated_by_user_id=owner_user_id,
        )
        self.session.add(allocation)
        if subscription.workspace_id is None:
            subscription.workspace_id = workspace.id
        self._audit(
            account=account,
            subscription=subscription,
            workspace_id=workspace.id,
            actor_user_id=owner_user_id,
            action="WORKSPACE_PROVISIONED",
        )
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def require_owned_subscription(
        self, owner_user_id: uuid.UUID, subscription_id: uuid.UUID
    ) -> WorkspaceSubscription:
        subscription = await self.session.get(WorkspaceSubscription, subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError()
        account = await self.session.get(
            BillingAccount, subscription.billing_account_id
        )
        if account is None or account.owner_user_id != owner_user_id:
            raise BillingAccountAccessDeniedError()
        return subscription

    def _audit(
        self,
        *,
        account: BillingAccount,
        actor_user_id: uuid.UUID,
        action: str,
        subscription: WorkspaceSubscription | None = None,
        workspace_id: uuid.UUID | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.session.add(
            BillingAuditEvent(
                billing_account_id=account.id,
                subscription_id=subscription.id if subscription else None,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                action=action,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
            )
        )
        AuditService(self.session).record(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            actor_type=AuditActorType.USER,
            action=action,
            area=AuditArea.BILLING,
            resource_type=(
                "WorkspaceSubscription" if subscription else "BillingAccount"
            ),
            resource_id=subscription.id if subscription else account.id,
            metadata={
                **({"previous_status": old_status} if old_status else {}),
                **({"new_status": new_status} if new_status else {}),
                "reason_provided": bool(reason),
            },
        )
