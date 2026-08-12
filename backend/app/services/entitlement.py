"""Central SaaS subscription, entitlement, and usage evaluation."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EntitlementDeniedError,
    EntitlementQuotaExceededError,
    SubscriptionRequiredError,
)
from app.models.action import ActionDefinition
from app.models.billing import (
    BillingInterval,
    EntitlementKind,
    PlanEntitlement,
    SaaSPlan,
    SaaSUsageRecord,
    SubscriptionStatus,
    WorkspaceSubscription,
)
from app.models.knowledge_document import KnowledgeDocument, KnowledgeDocumentStatus
from app.models.workspace_member import WorkspaceMember

TEAM_MEMBERS = "team.members"
ACTION_TYPES = "actions.types"
KNOWLEDGE_DOCUMENTS = "knowledge.documents"
AI_REQUESTS = "ai.requests"
AI_TOKENS = "ai.tokens"
SLIP_VERIFICATIONS = "payments.slip_verification"

_REFERENCE_ENTITLEMENTS = {
    "channels.webchat": (EntitlementKind.BOOLEAN, True, None),
    "channels.line": (EntitlementKind.BOOLEAN, True, None),
    "channels.facebook": (EntitlementKind.BOOLEAN, True, None),
    "ai.enabled": (EntitlementKind.BOOLEAN, True, None),
    AI_REQUESTS: (EntitlementKind.LIMITED, True, 10_000),
    KNOWLEDGE_DOCUMENTS: (EntitlementKind.LIMITED, True, 100),
    "knowledge.enabled": (EntitlementKind.BOOLEAN, True, None),
    "actions.enabled": (EntitlementKind.BOOLEAN, True, None),
    ACTION_TYPES: (EntitlementKind.LIMITED, True, 100),
    TEAM_MEMBERS: (EntitlementKind.LIMITED, True, 20),
    "payments.customer": (EntitlementKind.BOOLEAN, True, None),
    SLIP_VERIFICATIONS: (EntitlementKind.BOOLEAN, False, None),
}


@dataclass(frozen=True, slots=True)
class EntitlementEvaluation:
    key: str
    kind: EntitlementKind
    enabled: bool
    limit: int | None
    used: int | None
    remaining: int | None
    overage_allowed: bool


class EntitlementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def provision_reference_subscription(self, workspace_id: uuid.UUID) -> None:
        """Development/reference bootstrap; pricing and limits remain data rows."""
        plan_id = uuid.UUID("92000000-0000-4000-8000-000000000001")
        await self.session.execute(
            insert(SaaSPlan)
            .values(
                id=plan_id,
                key="starter-reference",
                display_name="Starter (provisional)",
                is_active=True,
                billing_interval=BillingInterval.MONTH,
                price_minor=149000,
                currency="THB",
                pricing_note="Pricing v0.1 working hypothesis; not final",
            )
            .on_conflict_do_nothing(index_elements=["key"])
        )
        for key, (kind, enabled, limit_value) in _REFERENCE_ENTITLEMENTS.items():
            await self.session.execute(
                insert(PlanEntitlement)
                .values(
                    id=uuid.uuid4(),
                    plan_id=plan_id,
                    key=key,
                    kind=kind,
                    enabled=enabled,
                    limit_value=limit_value,
                    overage_allowed=False,
                )
                .on_conflict_do_nothing(constraint="uq_plan_entitlement_key")
            )
        now = datetime.now(UTC)
        await self.session.execute(
            insert(WorkspaceSubscription)
            .values(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                plan_id=plan_id,
                status=SubscriptionStatus.ACTIVE,
                billing_interval=BillingInterval.MONTH,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                provider="development",
            )
            .on_conflict_do_nothing(
                index_elements=["workspace_id"],
                index_where=WorkspaceSubscription.status.in_(
                    [
                        SubscriptionStatus.TRIALING,
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.PAST_DUE,
                    ]
                ),
            )
        )

    async def current_subscription(self, workspace_id: uuid.UUID):
        return await self.session.scalar(
            select(WorkspaceSubscription)
            .where(
                WorkspaceSubscription.workspace_id == workspace_id,
                WorkspaceSubscription.status.in_(
                    [
                        SubscriptionStatus.TRIALING,
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.PAST_DUE,
                    ]
                ),
            )
            .order_by(WorkspaceSubscription.created_at.desc())
        )

    async def latest_subscription(self, workspace_id: uuid.UUID):
        return await self.session.scalar(
            select(WorkspaceSubscription)
            .where(WorkspaceSubscription.workspace_id == workspace_id)
            .order_by(WorkspaceSubscription.created_at.desc())
            .limit(1)
        )

    async def list_plans(self):
        return list(
            await self.session.scalars(
                select(SaaSPlan)
                .where(SaaSPlan.is_active.is_(True))
                .order_by(SaaSPlan.created_at)
            )
        )

    async def plan_entitlements(self, plan_id: uuid.UUID):
        return list(
            await self.session.scalars(
                select(PlanEntitlement)
                .where(PlanEntitlement.plan_id == plan_id)
                .order_by(PlanEntitlement.key)
            )
        )

    async def evaluate(
        self, workspace_id: uuid.UUID, key: str
    ) -> EntitlementEvaluation:
        subscription = await self.current_subscription(workspace_id)
        now = datetime.now(UTC)
        if (
            subscription is None
            or subscription.status
            not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}
            or subscription.current_period_end <= now
        ):
            raise SubscriptionRequiredError()
        plan = await self.session.get(SaaSPlan, subscription.plan_id)
        if plan is None or not plan.is_active:
            raise SubscriptionRequiredError()
        entitlement = await self.session.scalar(
            select(PlanEntitlement).where(
                PlanEntitlement.plan_id == plan.id,
                PlanEntitlement.key == key,
            )
        )
        if entitlement is None or not entitlement.enabled:
            raise EntitlementDeniedError(details={"entitlement": key})
        used = await self._usage(workspace_id, key, subscription)
        remaining = None
        if entitlement.kind == EntitlementKind.LIMITED:
            remaining = max((entitlement.limit_value or 0) - used, 0)
        return EntitlementEvaluation(
            key,
            entitlement.kind,
            entitlement.enabled,
            entitlement.limit_value,
            used,
            remaining,
            entitlement.overage_allowed,
        )

    async def require(self, workspace_id: uuid.UUID, key: str, quantity: int = 1):
        result = await self.evaluate(workspace_id, key)
        if (
            result.kind == EntitlementKind.LIMITED
            and not result.overage_allowed
            and (result.remaining is None or result.remaining < quantity)
        ):
            raise EntitlementQuotaExceededError(details={"entitlement": key})
        return result

    async def require_capacity(self, workspace_id: uuid.UUID, key: str) -> None:
        await self.session.execute(
            select(func.pg_advisory_xact_lock(self._lock_id(workspace_id, key)))
        )
        await self.require(workspace_id, key, 1)

    async def record(
        self,
        workspace_id: uuid.UUID,
        meter: str,
        quantity: int,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.session.add(
            SaaSUsageRecord(
                workspace_id=workspace_id,
                meter=meter,
                quantity=quantity,
                occurred_at=datetime.now(UTC),
                provider=provider,
                model=model,
            )
        )

    async def _usage(self, workspace_id, key, subscription) -> int:
        model = {
            TEAM_MEMBERS: WorkspaceMember,
            ACTION_TYPES: ActionDefinition,
            KNOWLEDGE_DOCUMENTS: KnowledgeDocument,
        }.get(key)
        if model is not None:
            conditions = [model.workspace_id == workspace_id]
            if model is KnowledgeDocument:
                conditions.append(
                    KnowledgeDocument.status != KnowledgeDocumentStatus.DELETED
                )
            return int(
                await self.session.scalar(
                    select(func.count()).select_from(model).where(*conditions)
                )
                or 0
            )
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(SaaSUsageRecord.quantity), 0)).where(
                    SaaSUsageRecord.workspace_id == workspace_id,
                    SaaSUsageRecord.meter == key,
                    SaaSUsageRecord.occurred_at >= subscription.current_period_start,
                    SaaSUsageRecord.occurred_at < subscription.current_period_end,
                )
            )
            or 0
        )

    @staticmethod
    def _lock_id(workspace_id: uuid.UUID, key: str) -> int:
        value = int.from_bytes(
            hashlib.sha256(f"{workspace_id}:{key}".encode()).digest()[:8],
            "big",
            signed=False,
        )
        return value - 2**64 if value >= 2**63 else value
