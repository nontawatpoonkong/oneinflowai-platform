"""Add the durable hotel automation foundation.

Revision ID: 1b2c3d4e5f6a
Revises: 0a1b2c3d4e5f
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1b2c3d4e5f6a"
down_revision: str | None = "0a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_domain_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("available_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("deduplication_key", sa.String(255), nullable=False),
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
        sa.CheckConstraint("attempt_count >= 0", name="ck_automation_event_attempts"),
        sa.CheckConstraint("event_version > 0", name="ck_automation_event_version"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "deduplication_key", name="uq_automation_event_dedupe"
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_automation_event_scope"),
    )
    op.create_index(
        "ix_automation_events_claim",
        "automation_domain_events",
        ["state", "available_at", "created_at"],
    )
    op.create_index(
        "ix_automation_events_workspace_type",
        "automation_domain_events",
        ["workspace_id", "event_type"],
    )

    op.create_table(
        "automation_definitions",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("trigger_event_type", sa.String(128), nullable=False),
        sa.Column("trigger_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "conditions",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("action_config", postgresql.JSONB(), nullable=False),
        sa.Column("schedule_mode", sa.String(32), nullable=False),
        sa.Column(
            "schedule_config",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
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
        sa.CheckConstraint("trigger_version > 0", name="ck_automation_trigger_version"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_automation_definition_scope"
        ),
    )
    op.create_index(
        "ix_automation_definitions_trigger",
        "automation_definitions",
        ["workspace_id", "trigger_event_type"],
    )

    op.create_table(
        "automation_executions",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("automation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("scheduled_for", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("effect_key", sa.String(255), nullable=False),
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
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_automation_execution_attempts"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "automation_id"],
            ["automation_definitions.workspace_id", "automation_definitions.id"],
            name="fk_automation_execution_definition_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "event_id"],
            ["automation_domain_events.workspace_id", "automation_domain_events.id"],
            name="fk_automation_execution_event_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("effect_key"),
        sa.UniqueConstraint(
            "automation_id", "event_id", name="uq_automation_execution_event"
        ),
    )
    op.create_index(
        "ix_automation_executions_claim",
        "automation_executions",
        ["status", "scheduled_for"],
    )
    op.create_index(
        "ix_automation_executions_workspace_created",
        "automation_executions",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_executions_workspace_created", table_name="automation_executions"
    )
    op.drop_index("ix_automation_executions_claim", table_name="automation_executions")
    op.drop_table("automation_executions")
    op.drop_index(
        "ix_automation_definitions_trigger", table_name="automation_definitions"
    )
    op.drop_table("automation_definitions")
    op.drop_index(
        "ix_automation_events_workspace_type", table_name="automation_domain_events"
    )
    op.drop_index("ix_automation_events_claim", table_name="automation_domain_events")
    op.drop_table("automation_domain_events")
