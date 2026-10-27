"""Add account billing and Workspace provisioning foundation.

Revision ID: 5f6a7b8c9d0
Revises: 4e5f6a7b8c9
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5f6a7b8c9d0"
down_revision: str | None = "4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

billing_account_status = postgresql.ENUM(
    "ACTIVE", "SUSPENDED", name="billing_account_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        "ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS "
        "'PENDING_ACTIVATION' BEFORE 'TRIALING'"
    )
    billing_account_status.create(bind, checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "is_platform_admin", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.create_table(
        "billing_accounts",
        sa.Column(
            "owner_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "status", billing_account_status, server_default="ACTIVE", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", name="uq_billing_account_owner"),
    )
    op.create_index(
        "ix_billing_accounts_owner_user_id",
        "billing_accounts",
        ["owner_user_id"],
        unique=False,
    )
    op.add_column(
        "workspace_subscriptions",
        sa.Column(
            "billing_account_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "workspace_subscriptions",
        sa.Column(
            "workspace_limit", sa.BigInteger(), server_default="1", nullable=False
        ),
    )
    op.alter_column(
        "workspace_subscriptions",
        "workspace_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )

    owner_rows = bind.execute(
        sa.text(
            "SELECT DISTINCT w.owner_id "
            "FROM workspace_subscriptions s "
            "JOIN workspaces w ON w.id = s.workspace_id"
        )
    ).fetchall()
    for row in owner_rows:
        owner_id = row[0]
        account_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"oneinflowai:billing-account:{owner_id}"
        )
        bind.execute(
            sa.text(
                "INSERT INTO billing_accounts "
                "(id, owner_user_id, status, created_at, updated_at) "
                "VALUES (:id, :owner, 'ACTIVE', now(), now()) "
                "ON CONFLICT (owner_user_id) DO NOTHING"
            ),
            {"id": account_id, "owner": owner_id},
        )

    subscription_rows = bind.execute(
        sa.text(
            "SELECT s.id, s.workspace_id, w.owner_id "
            "FROM workspace_subscriptions s "
            "JOIN workspaces w ON w.id = s.workspace_id"
        )
    ).fetchall()
    for subscription_id, _workspace_id, owner_id in subscription_rows:
        account_id = bind.execute(
            sa.text(
                "SELECT id FROM billing_accounts WHERE owner_user_id = :owner"
            ),
            {"owner": owner_id},
        ).scalar_one()
        bind.execute(
            sa.text(
                "UPDATE workspace_subscriptions "
                "SET billing_account_id = :account WHERE id = :subscription"
            ),
            {"account": account_id, "subscription": subscription_id},
        )

    missing = bind.execute(
        sa.text(
            "SELECT count(*) FROM workspace_subscriptions "
            "WHERE billing_account_id IS NULL"
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(
            "Cannot deterministically assign BillingAccount to existing subscriptions"
        )

    op.alter_column(
        "workspace_subscriptions",
        "billing_account_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_workspace_subscription_billing_account",
        "workspace_subscriptions",
        "billing_accounts",
        ["billing_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_workspace_subscriptions_billing_account",
        "workspace_subscriptions",
        ["billing_account_id", "status"],
    )
    op.create_table(
        "subscription_workspace_allocations",
        sa.Column(
            "subscription_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "allocated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["workspace_subscriptions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["allocated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id", "workspace_id", name="uq_subscription_workspace"
        ),
        sa.UniqueConstraint("workspace_id", name="uq_workspace_billing_allocation"),
    )
    op.create_index(
        "ix_subscription_workspace_allocations_subscription_id",
        "subscription_workspace_allocations",
        ["subscription_id"],
    )
    op.create_index(
        "ix_subscription_workspace_allocations_workspace_id",
        "subscription_workspace_allocations",
        ["workspace_id"],
    )
    for subscription_id, workspace_id, owner_id in subscription_rows:
        allocation_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"oneinflowai:subscription-allocation:{subscription_id}:{workspace_id}",
        )
        bind.execute(
            sa.text(
                "INSERT INTO subscription_workspace_allocations "
                "(id, subscription_id, workspace_id, allocated_by_user_id, "
                "created_at, updated_at) "
                "VALUES (:id, :subscription, :workspace, :owner, now(), now())"
            ),
            {
                "id": allocation_id,
                "subscription": subscription_id,
                "workspace": workspace_id,
                "owner": owner_id,
            },
        )

    op.create_table(
        "billing_audit_events",
        sa.Column(
            "billing_account_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True)),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("old_status", sa.String(32)),
        sa.Column("new_status", sa.String(32)),
        sa.Column("reason", sa.String(500)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["billing_account_id"], ["billing_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["workspace_subscriptions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_billing_audit_account_created",
        "billing_audit_events",
        ["billing_account_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    pending = bind.execute(
        sa.text(
            "SELECT count(*) FROM workspace_subscriptions "
            "WHERE workspace_id IS NULL OR status::text = 'PENDING_ACTIVATION'"
        )
    ).scalar_one()
    if pending:
        raise RuntimeError(
            "Downgrade blocked: pre-Workspace subscriptions must be resolved first"
        )
    non_legacy_allocations = bind.execute(
        sa.text(
            "SELECT count(*) FROM subscription_workspace_allocations a "
            "JOIN workspace_subscriptions s ON s.id = a.subscription_id "
            "WHERE a.workspace_id IS DISTINCT FROM s.workspace_id"
        )
    ).scalar_one()
    if non_legacy_allocations:
        raise RuntimeError(
            "Downgrade blocked: allocations not representable by legacy "
            "Workspace linkage"
        )

    op.drop_index("ix_billing_audit_account_created", table_name="billing_audit_events")
    op.drop_table("billing_audit_events")
    op.drop_index(
        "ix_subscription_workspace_allocations_workspace_id",
        table_name="subscription_workspace_allocations",
    )
    op.drop_index(
        "ix_subscription_workspace_allocations_subscription_id",
        table_name="subscription_workspace_allocations",
    )
    op.drop_table("subscription_workspace_allocations")
    op.drop_index(
        "ix_workspace_subscriptions_billing_account",
        table_name="workspace_subscriptions",
    )
    op.drop_constraint(
        "fk_workspace_subscription_billing_account",
        "workspace_subscriptions",
        type_="foreignkey",
    )
    op.drop_column("workspace_subscriptions", "workspace_limit")
    op.drop_column("workspace_subscriptions", "billing_account_id")
    op.alter_column(
        "workspace_subscriptions",
        "workspace_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_index("ix_billing_accounts_owner_user_id", table_name="billing_accounts")
    op.drop_table("billing_accounts")
    op.drop_column("users", "is_platform_admin")
    billing_account_status.drop(bind, checkfirst=True)

    op.drop_index(
        "uq_workspace_effective_subscription",
        table_name="workspace_subscriptions",
    )
    op.execute(
        "ALTER TABLE workspace_subscriptions ALTER COLUMN status TYPE VARCHAR(32) "
        "USING status::text"
    )
    op.execute("DROP TYPE subscription_status")
    op.execute(
        "CREATE TYPE subscription_status AS ENUM "
        "('TRIALING','ACTIVE','PAST_DUE','CANCELED','EXPIRED')"
    )
    op.execute(
        "ALTER TABLE workspace_subscriptions ALTER COLUMN status "
        "TYPE subscription_status USING status::subscription_status"
    )
    op.create_index(
        "uq_workspace_effective_subscription",
        "workspace_subscriptions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('TRIALING', 'ACTIVE', 'PAST_DUE')"
        ),
    )
