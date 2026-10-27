"""campaign operations: lifecycle markers and scheduled job state

Revision ID: 1f2a3b4c5d6
Revises: 0e1f2a3b4c5
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1f2a3b4c5d6"
down_revision: str | None = "0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promotion_campaigns",
        sa.Column(
            "management_origin",
            sa.String(length=16),
            nullable=False,
            server_default="WORKSPACE",
        ),
    )
    op.add_column(
        "promotion_campaigns",
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_promotion_campaign_origin",
        "promotion_campaigns",
        "management_origin IN ('WORKSPACE','PLATFORM')",
    )
    op.create_index(
        "ix_promotion_campaign_lifecycle_expiry",
        "promotion_campaigns",
        ["status", "valid_until"],
    )
    op.create_index(
        "ix_promotion_campaign_lifecycle_start",
        "promotion_campaigns",
        ["status", "valid_from"],
        postgresql_where=sa.text("started_at IS NULL"),
    )
    # Campaigns already ACTIVE inside their window have started; mark them so
    # the scheduler does not emit retroactive start events after upgrade.
    op.execute(
        "UPDATE promotion_campaigns SET started_at = now() "
        "WHERE status = 'ACTIVE' AND (valid_from IS NULL OR valid_from <= now())"
    )
    op.create_table(
        "scheduled_job_states",
        sa.Column("job_name", sa.String(length=64), primary_key=True),
        sa.Column("last_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_succeeded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_worker_id", sa.String(length=128), nullable=True),
        sa.Column("last_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0", name="ck_scheduled_job_failures"
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduled_job_states")
    op.drop_index(
        "ix_promotion_campaign_lifecycle_start", table_name="promotion_campaigns"
    )
    op.drop_index(
        "ix_promotion_campaign_lifecycle_expiry", table_name="promotion_campaigns"
    )
    op.drop_constraint(
        "ck_promotion_campaign_origin", "promotion_campaigns", type_="check"
    )
    op.drop_column("promotion_campaigns", "started_at")
    op.drop_column("promotion_campaigns", "management_origin")
