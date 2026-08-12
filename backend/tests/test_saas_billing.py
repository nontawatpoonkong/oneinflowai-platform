"""Sprint 9.2 SaaS billing, entitlement, usage, and isolation tests."""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    EntitlementDeniedError,
    EntitlementQuotaExceededError,
    SubscriptionRequiredError,
)
from app.models.billing import (
    BillingInterval,
    EntitlementKind,
    PlanEntitlement,
    SaaSPlan,
    SaaSUsageRecord,
    SubscriptionStatus,
    WorkspaceSubscription,
)
from app.models.payment import Payment
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.entitlement import (
    ACTION_TYPES,
    AI_REQUESTS,
    TEAM_MEMBERS,
    EntitlementService,
)
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_action_definitions import _payload


def _register(client: TestClient, email: str):
    data, token = register_verify_and_login(client, email=email)
    return data, {"Authorization": f"Bearer {token}"}


async def _subscription(workspace_id: str):
    async with TestSessionLocal() as session:
        return await EntitlementService(session).latest_subscription(
            uuid.UUID(workspace_id)
        )


async def _set_entitlement(
    workspace_id: str, key: str, *, kind=None, enabled=None, limit=None
):
    async with TestSessionLocal() as session:
        subscription = await EntitlementService(session).latest_subscription(
            uuid.UUID(workspace_id)
        )
        item = await session.scalar(
            select(PlanEntitlement).where(
                PlanEntitlement.plan_id == subscription.plan_id,
                PlanEntitlement.key == key,
            )
        )
        if kind is not None:
            item.kind = kind
        if enabled is not None:
            item.enabled = enabled
        if limit is not None:
            item.limit_value = limit
        await session.commit()


def test_plan_subscription_and_entitlement_read_api(client_db: TestClient):
    data, headers = _register(client_db, "billing-owner@example.com")
    plans = client_db.get("/api/v1/billing/plans", headers=headers)
    subscription = client_db.get("/api/v1/billing/subscription", headers=headers)
    entitlements = client_db.get("/api/v1/billing/entitlements", headers=headers)
    usage = client_db.get("/api/v1/billing/usage", headers=headers)

    assert plans.status_code == subscription.status_code == 200
    assert entitlements.status_code == usage.status_code == 200
    current = subscription.json()["data"]
    assert current["workspace_id"] == data["workspace"]["id"]
    assert current["plan"]["pricing_note"].endswith("not final")
    assert {item["kind"] for item in current["plan"]["entitlements"]} >= {
        "BOOLEAN",
        "LIMITED",
    }


@pytest.mark.parametrize(
    "role", [WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER]
)
def test_billing_read_allowed_for_workspace_members_but_no_mutation(client_db, role):
    data, headers = _register(client_db, f"billing-{role.value}@example.com")

    async def update_role():
        async with TestSessionLocal() as session:
            member = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == uuid.UUID(data["workspace"]["id"])
                )
            )
            member.role = role
            await session.commit()

    asyncio.run(update_role())
    assert (
        client_db.get("/api/v1/billing/subscription", headers=headers).status_code
        == 200
    )
    assert (
        client_db.post(
            "/api/v1/billing/subscription", headers=headers, json={"plan": "business"}
        ).status_code
        == 405
    )


def test_workspace_subscription_isolation_and_single_effective_constraint(client_db):
    first, first_headers = _register(client_db, "billing-first@example.com")
    second, second_headers = _register(client_db, "billing-second@example.com")
    first_view = client_db.get(
        "/api/v1/billing/subscription", headers=first_headers
    ).json()["data"]
    second_view = client_db.get(
        "/api/v1/billing/subscription", headers=second_headers
    ).json()["data"]
    assert first_view["workspace_id"] == first["workspace"]["id"]
    assert second_view["workspace_id"] == second["workspace"]["id"]
    assert first_view["id"] != second_view["id"]

    async def duplicate():
        async with TestSessionLocal() as session:
            existing = await EntitlementService(session).latest_subscription(
                uuid.UUID(first["workspace"]["id"])
            )
            session.add(
                WorkspaceSubscription(
                    workspace_id=existing.workspace_id,
                    plan_id=existing.plan_id,
                    status=SubscriptionStatus.ACTIVE,
                    billing_interval=BillingInterval.MONTH,
                    current_period_start=datetime.now(UTC),
                    current_period_end=datetime.now(UTC) + timedelta(days=30),
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(duplicate())


def test_boolean_limited_unlimited_missing_and_inactive_plan(client_db):
    data, _ = _register(client_db, "billing-semantics@example.com")
    workspace_id = data["workspace"]["id"]

    async def evaluate():
        async with TestSessionLocal() as session:
            service = EntitlementService(session)
            boolean = await service.require(uuid.UUID(workspace_id), "ai.enabled")
            assert boolean.kind == EntitlementKind.BOOLEAN
            limited = await service.require(uuid.UUID(workspace_id), ACTION_TYPES)
            assert limited.limit == 100 and limited.remaining == 100
            item = await session.scalar(
                select(PlanEntitlement).where(PlanEntitlement.key == ACTION_TYPES)
            )
            item.kind, item.limit_value = EntitlementKind.UNLIMITED, None
            await session.flush()
            unlimited = await service.require(uuid.UUID(workspace_id), ACTION_TYPES)
            assert (
                unlimited.kind == EntitlementKind.UNLIMITED
                and unlimited.remaining is None
            )
            with pytest.raises(EntitlementDeniedError):
                await service.require(uuid.UUID(workspace_id), "missing.feature")
            plan = await session.get(
                SaaSPlan,
                (await service.latest_subscription(uuid.UUID(workspace_id))).plan_id,
            )
            plan.is_active = False
            await session.flush()
            with pytest.raises(SubscriptionRequiredError):
                await service.require(uuid.UUID(workspace_id), "ai.enabled")

    asyncio.run(evaluate())


@pytest.mark.parametrize(
    "status",
    [
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.CANCELED,
        SubscriptionStatus.EXPIRED,
    ],
)
def test_non_active_subscription_denies_capability_without_deleting_data(
    client_db, status
):
    data, _ = _register(client_db, f"billing-{status.value}@example.com")

    async def check():
        async with TestSessionLocal() as session:
            service = EntitlementService(session)
            item = await service.latest_subscription(uuid.UUID(data["workspace"]["id"]))
            item.status = status
            await session.commit()
        async with TestSessionLocal() as session:
            with pytest.raises(SubscriptionRequiredError):
                await EntitlementService(session).require(
                    uuid.UUID(data["workspace"]["id"]), "ai.enabled"
                )
            assert await session.get(WorkspaceSubscription, item.id) is not None

    asyncio.run(check())


def test_derived_and_metered_usage_align_to_subscription_period(client_db):
    data, _ = _register(client_db, "billing-usage@example.com")
    workspace_id = uuid.UUID(data["workspace"]["id"])

    async def check():
        async with TestSessionLocal() as session:
            service = EntitlementService(session)
            members = await service.evaluate(workspace_id, TEAM_MEMBERS)
            assert members.used == 1 and members.remaining == 19
            await service.record(
                workspace_id, AI_REQUESTS, 3, provider="test", model="test-model"
            )
            subscription = await service.latest_subscription(workspace_id)
            session.add(
                SaaSUsageRecord(
                    workspace_id=workspace_id,
                    meter=AI_REQUESTS,
                    quantity=99,
                    occurred_at=subscription.current_period_start
                    - timedelta(seconds=1),
                )
            )
            await session.commit()
        async with TestSessionLocal() as session:
            usage = await EntitlementService(session).evaluate(
                workspace_id, AI_REQUESTS
            )
            assert usage.used == 3 and usage.remaining == 9997

    asyncio.run(check())


def test_action_type_limit_is_concurrency_safe(client_db):
    data, headers = _register(client_db, "billing-action-race@example.com")
    asyncio.run(_set_entitlement(data["workspace"]["id"], ACTION_TYPES, limit=1))

    def create(key):
        return client_db.post(
            "/api/v1/actions/definitions", headers=headers, json=_payload(key)
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(create, ["race_a", "race_b"]))
    assert statuses == [201, 409]


def test_team_seat_limit_lock_prevents_concurrent_bypass(client_db):
    owner, _ = _register(client_db, "billing-seat-owner@example.com")
    first, _ = _register(client_db, "billing-seat-first@example.com")
    second, _ = _register(client_db, "billing-seat-second@example.com")
    workspace_id = uuid.UUID(owner["workspace"]["id"])
    asyncio.run(_set_entitlement(str(workspace_id), TEAM_MEMBERS, limit=2))

    async def add(user_id):
        try:
            async with TestSessionLocal() as session:
                await EntitlementService(session).require_capacity(
                    workspace_id, TEAM_MEMBERS
                )
                session.add(
                    WorkspaceMember(
                        workspace_id=workspace_id,
                        user_id=uuid.UUID(user_id),
                        role=WorkspaceRole.MEMBER,
                    )
                )
                await session.commit()
            return "added"
        except EntitlementQuotaExceededError:
            return "denied"

    async def race():
        return await asyncio.gather(add(first["user"]["id"]), add(second["user"]["id"]))

    assert sorted(asyncio.run(race())) == ["added", "denied"]


def test_customer_payment_domain_is_not_saas_billing(client_db):
    data, headers = _register(client_db, "billing-domain@example.com")

    async def payment_count():
        async with TestSessionLocal() as session:
            return int(
                await session.scalar(select(func.count()).select_from(Payment)) or 0
            )

    before = asyncio.run(payment_count())
    assert (
        client_db.get("/api/v1/billing/subscription", headers=headers).status_code
        == 200
    )
    after = asyncio.run(payment_count())
    assert before == after == 0
    assert asyncio.run(_subscription(data["workspace"]["id"])) is not None
