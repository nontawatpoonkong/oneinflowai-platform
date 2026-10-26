"""global audit and product usage analytics

Revision ID: 8c9d0e1f2a3
Revises: 7b8c9d0e1f2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8c9d0e1f2a3"
down_revision: str | None = "7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_audit_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("action", sa.String(96), nullable=False),
        sa.Column("area", sa.String(32), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("route", sa.String(255)),
        sa.Column("request_method", sa.String(8)),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column(
            "safe_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('USER','SYSTEM','AI','AUTOMATION','PLATFORM_ADMIN')",
            name="ck_workspace_audit_actor_type",
        ),
        sa.CheckConstraint(
            "result IN ('SUCCESS','DENIED','FAILED')",
            name="ck_workspace_audit_result",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_audit_workspace_occurred",
        "workspace_audit_events",
        ["workspace_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_workspace_audit_actor_occurred",
        "workspace_audit_events",
        ["actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_workspace_audit_action_occurred",
        "workspace_audit_events",
        ["action", "occurred_at"],
    )
    op.create_index(
        "ix_workspace_audit_area_occurred",
        "workspace_audit_events",
        ["area", "occurred_at"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_workspace_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'workspace_audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER workspace_audit_events_immutable
        BEFORE UPDATE OR DELETE ON workspace_audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_workspace_audit_mutation()
        """
    )

    op.create_table(
        "product_usage_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("session_id", sa.String(128)),
        sa.Column("navigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_name", sa.String(32), nullable=False),
        sa.Column("page_path", sa.String(255), nullable=False),
        sa.Column("feature", sa.String(32)),
        sa.Column(
            "safe_properties",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "event_name IN ('PAGE_VIEW')", name="ck_product_usage_event_name"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "event_name",
            "navigation_id",
            name="uq_product_usage_navigation",
        ),
    )
    op.create_index(
        "ix_product_usage_workspace_occurred",
        "product_usage_events",
        ["workspace_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_product_usage_workspace_feature",
        "product_usage_events",
        ["workspace_id", "feature", "occurred_at"],
    )
    op.create_index(
        "ix_product_usage_user_occurred",
        "product_usage_events",
        ["user_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_usage_user_occurred", table_name="product_usage_events")
    op.drop_index(
        "ix_product_usage_workspace_feature", table_name="product_usage_events"
    )
    op.drop_index(
        "ix_product_usage_workspace_occurred", table_name="product_usage_events"
    )
    op.drop_table("product_usage_events")
    op.execute(
        "DROP TRIGGER workspace_audit_events_immutable ON workspace_audit_events"
    )
    op.execute("DROP FUNCTION reject_workspace_audit_mutation()")
    op.drop_index(
        "ix_workspace_audit_area_occurred", table_name="workspace_audit_events"
    )
    op.drop_index(
        "ix_workspace_audit_action_occurred", table_name="workspace_audit_events"
    )
    op.drop_index(
        "ix_workspace_audit_actor_occurred", table_name="workspace_audit_events"
    )
    op.drop_index(
        "ix_workspace_audit_workspace_occurred", table_name="workspace_audit_events"
    )
    op.drop_table("workspace_audit_events")
