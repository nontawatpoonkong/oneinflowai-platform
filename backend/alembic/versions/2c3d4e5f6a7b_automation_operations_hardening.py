"""Add automation worker operations metadata.

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f6a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2c3d4e5f6a7b"
down_revision: str | None = "1b2c3d4e5f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "automation_executions",
        sa.Column(
            "manual_retry_count", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "automation_executions",
        sa.Column(
            "terminal_failure", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column(
        "automation_executions",
        sa.Column("claimed_by_worker_id", sa.String(128)),
    )
    op.add_column(
        "automation_executions",
        sa.Column("last_recovered_at", sa.TIMESTAMP(timezone=True)),
    )
    op.add_column(
        "automation_executions",
        sa.Column(
            "failure_history",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_automation_execution_manual_retries",
        "automation_executions",
        "manual_retry_count >= 0",
    )
    op.create_index(
        "ix_automation_executions_stale",
        "automation_executions",
        ["status", "started_at"],
    )

    op.create_table(
        "automation_worker_heartbeats",
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), server_default="STARTING", nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_successful_poll_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("build_identifier", sa.String(128)),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", name="uq_automation_worker_heartbeat_id"),
    )
    op.create_index(
        "ix_automation_worker_heartbeat_last_seen",
        "automation_worker_heartbeats",
        ["last_heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_worker_heartbeat_last_seen",
        table_name="automation_worker_heartbeats",
    )
    op.drop_table("automation_worker_heartbeats")
    op.drop_index("ix_automation_executions_stale", table_name="automation_executions")
    op.drop_constraint(
        "ck_automation_execution_manual_retries",
        "automation_executions",
        type_="check",
    )
    op.drop_column("automation_executions", "failure_history")
    op.drop_column("automation_executions", "last_recovered_at")
    op.drop_column("automation_executions", "claimed_by_worker_id")
    op.drop_column("automation_executions", "terminal_failure")
    op.drop_column("automation_executions", "manual_retry_count")
