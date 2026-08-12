"""SaaS billing plans, subscriptions, entitlements, and usage

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

billing_interval = postgresql.ENUM(
    "MONTH", "YEAR", name="billing_interval", create_type=False
)
entitlement_kind = postgresql.ENUM(
    "BOOLEAN", "LIMITED", "UNLIMITED", name="entitlement_kind", create_type=False
)
subscription_status = postgresql.ENUM(
    "TRIALING", "ACTIVE", "PAST_DUE", "CANCELED", "EXPIRED",
    name="subscription_status", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    billing_interval.create(bind, checkfirst=True)
    entitlement_kind.create(bind, checkfirst=True)
    subscription_status.create(bind, checkfirst=True)
    op.create_table(
        "saas_plans",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("billing_interval", billing_interval, nullable=False),
        sa.Column("price_minor", sa.BigInteger()),
        sa.Column("currency", sa.String(3)),
        sa.Column("pricing_note", sa.String(255)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("key", name="uq_saas_plans_key"),
    )
    op.create_table(
        "plan_entitlements",
        sa.Column(
            "plan_id",
            sa.Uuid(),
            sa.ForeignKey("saas_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(96), nullable=False),
        sa.Column("kind", entitlement_kind, nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("limit_value", sa.BigInteger()),
        sa.Column(
            "overage_allowed", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("plan_id", "key", name="uq_plan_entitlement_key"),
    )
    op.create_index("ix_plan_entitlements_plan_id", "plan_entitlements", ["plan_id"])
    op.create_table(
        "workspace_subscriptions",
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            sa.Uuid(),
            sa.ForeignKey("saas_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", subscription_status, nullable=False),
        sa.Column("billing_interval", billing_interval, nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial_end", sa.DateTime(timezone=True)),
        sa.Column(
            "cancel_at_period_end", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
        sa.Column("provider", sa.String(64)),
        sa.Column("provider_customer_ref", sa.String(255)),
        sa.Column("provider_subscription_ref", sa.String(255)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_workspace_subscription_lookup",
        "workspace_subscriptions",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_workspace_subscriptions_plan_id", "workspace_subscriptions", ["plan_id"]
    )
    op.create_index(
        "uq_workspace_effective_subscription",
        "workspace_subscriptions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('TRIALING', 'ACTIVE', 'PAST_DUE')"),
    )
    op.create_table(
        "saas_usage_records",
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("meter", sa.String(96), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("model", sa.String(128)),
        sa.Column("id", sa.Uuid(), primary_key=True),
    )
    op.create_index(
        "ix_saas_usage_period",
        "saas_usage_records",
        ["workspace_id", "meter", "occurred_at"],
    )
    _seed_reference_data(bind)


def _seed_reference_data(bind) -> None:
    plan_ids = {
        "starter-reference": uuid.UUID("92000000-0000-4000-8000-000000000001"),
        "growth-reference": uuid.UUID("92000000-0000-4000-8000-000000000002"),
        "business-reference": uuid.UUID("92000000-0000-4000-8000-000000000003"),
        "enterprise-reference": uuid.UUID("92000000-0000-4000-8000-000000000004"),
    }
    prices = {
        "starter-reference": 149000,
        "growth-reference": 299000,
        "business-reference": 599000,
        "enterprise-reference": None,
    }
    for key, plan_id in plan_ids.items():
        bind.execute(
            sa.text(
                "INSERT INTO saas_plans "
                "(id,key,display_name,is_active,billing_interval,price_minor,"
                "currency,pricing_note) VALUES "
                "(:id,:key,:name,true,'MONTH',:price,'THB',:note)"
            ),
            {
                "id": plan_id,
                "key": key,
                "name": key.replace("-reference", "").title(),
                "price": prices[key],
                "note": "Pricing v0.1 working hypothesis; configurable and not final",
            },
        )
    base = {
        "channels.webchat": ("BOOLEAN", True, None),
        "channels.line": ("BOOLEAN", True, None),
        "channels.facebook": ("BOOLEAN", True, None),
        "ai.enabled": ("BOOLEAN", True, None),
        "ai.requests": ("LIMITED", True, 10000),
        "knowledge.enabled": ("BOOLEAN", True, None),
        "knowledge.documents": ("LIMITED", True, 100),
        "actions.enabled": ("BOOLEAN", True, None),
        "actions.types": ("LIMITED", True, 100),
        "team.members": ("LIMITED", True, 20),
        "payments.customer": ("BOOLEAN", True, None),
        "payments.slip_verification": ("BOOLEAN", False, None),
    }
    for plan_key, plan_id in plan_ids.items():
        for key, (kind, enabled, limit_value) in base.items():
            if key == "payments.slip_verification" and plan_key != "starter-reference":
                enabled = True
            if plan_key == "enterprise-reference" and kind == "LIMITED":
                kind, limit_value = "UNLIMITED", None
            bind.execute(
                sa.text(
                    "INSERT INTO plan_entitlements "
                    "(id,plan_id,key,kind,enabled,limit_value,overage_allowed) "
                    "VALUES (:id,:plan,:key,:kind,:enabled,:limit,false)"
                ),
                {
                    "id": uuid.uuid4(),
                    "plan": plan_id,
                    "key": key,
                    "kind": kind,
                    "enabled": enabled,
                    "limit": limit_value,
                },
            )
    now = datetime.now(UTC)
    bind.execute(
        sa.text(
            "INSERT INTO workspace_subscriptions "
            "(id,workspace_id,plan_id,status,billing_interval,"
            "current_period_start,current_period_end,provider) "
            "SELECT gen_random_uuid(),id,:plan,'ACTIVE','MONTH',"
            ":start,:end,'development' FROM workspaces"
        ),
        {
            "plan": plan_ids["starter-reference"],
            "start": now,
            "end": now + timedelta(days=30),
        },
    )


def downgrade() -> None:
    op.drop_index("ix_saas_usage_period", table_name="saas_usage_records")
    op.drop_table("saas_usage_records")
    op.drop_index(
        "uq_workspace_effective_subscription", table_name="workspace_subscriptions"
    )
    op.drop_index(
        "ix_workspace_subscriptions_plan_id", table_name="workspace_subscriptions"
    )
    op.drop_index(
        "ix_workspace_subscription_lookup", table_name="workspace_subscriptions"
    )
    op.drop_table("workspace_subscriptions")
    op.drop_index("ix_plan_entitlements_plan_id", table_name="plan_entitlements")
    op.drop_table("plan_entitlements")
    op.drop_table("saas_plans")
    subscription_status.drop(op.get_bind(), checkfirst=True)
    entitlement_kind.drop(op.get_bind(), checkfirst=True)
    billing_interval.drop(op.get_bind(), checkfirst=True)
