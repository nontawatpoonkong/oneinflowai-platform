"""Add read-only PMS adapter foundation.

Revision ID: 4e5f6a7b8c9
Revises: 3d4e5f6a7b8c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4e5f6a7b8c9"
down_revision: str | None = "3d4e5f6a7b8c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pms_connections",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("sync_mode", sa.String(32), nullable=False),
        sa.Column("inventory_authority", sa.String(16), nullable=False),
        sa.Column("credential_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("credential_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("credential_key_version", sa.String(32), nullable=False),
        sa.Column("external_account_id", sa.String(255)),
        sa.Column(
            "sync_cursor",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_successful_sync_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_failed_sync_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_error_code", sa.String(64)),
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
            "sync_mode = 'READ_ONLY_IMPORT'", name="ck_pms_connection_read_only"
        ),
        sa.CheckConstraint(
            "inventory_authority IN ('LOCAL', 'PMS')",
            name="ck_pms_connection_inventory_authority",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_pms_connection_scope"),
    )
    op.create_index(
        "ix_pms_connections_workspace_active",
        "pms_connections",
        ["workspace_id", "active"],
    )
    op.create_table(
        "pms_external_mappings",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("local_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_version", sa.String(255)),
        sa.Column("external_updated_at", sa.TIMESTAMP(timezone=True)),
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
            ["workspace_id", "connection_id"],
            ["pms_connections.workspace_id", "pms_connections.id"],
            ondelete="CASCADE",
            name="fk_pms_mapping_connection_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "entity_type",
            "external_id",
            name="uq_pms_mapping_external_identity",
        ),
    )
    op.create_index(
        "ix_pms_mappings_local",
        "pms_external_mappings",
        ["workspace_id", "entity_type", "local_entity_id"],
    )
    op.create_table(
        "pms_sync_runs",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "cursor_before",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cursor_after", postgresql.JSONB()),
        sa.Column("entities_fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("entities_applied", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conflict_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("warning_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["workspace_id", "connection_id"],
            ["pms_connections.workspace_id", "pms_connections.id"],
            ondelete="CASCADE",
            name="fk_pms_sync_run_connection_scope",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_pms_sync_run_scope"),
    )
    op.create_index(
        "uq_pms_sync_run_active_connection",
        "pms_sync_runs",
        ["connection_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
    )
    op.create_index(
        "ix_pms_sync_runs_workspace_created",
        "pms_sync_runs",
        ["workspace_id", "created_at"],
    )
    op.create_table(
        "pms_reconciliation_issues",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("local_entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("issue_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="OPEN", nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True)),
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
            ["workspace_id", "connection_id"],
            ["pms_connections.workspace_id", "pms_connections.id"],
            ondelete="CASCADE",
            name="fk_pms_issue_connection_scope",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "sync_run_id"],
            ["pms_sync_runs.workspace_id", "pms_sync_runs.id"],
            ondelete="CASCADE",
            name="fk_pms_issue_run_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_pms_issue_open_identity",
        "pms_reconciliation_issues",
        ["connection_id", "entity_type", "external_id", "issue_type"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )
    op.create_index(
        "ix_pms_issues_workspace_status",
        "pms_reconciliation_issues",
        ["workspace_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pms_issues_workspace_status", table_name="pms_reconciliation_issues"
    )
    op.drop_index("uq_pms_issue_open_identity", table_name="pms_reconciliation_issues")
    op.drop_table("pms_reconciliation_issues")
    op.drop_index("ix_pms_sync_runs_workspace_created", table_name="pms_sync_runs")
    op.drop_index("uq_pms_sync_run_active_connection", table_name="pms_sync_runs")
    op.drop_table("pms_sync_runs")
    op.drop_index("ix_pms_mappings_local", table_name="pms_external_mappings")
    op.drop_table("pms_external_mappings")
    op.drop_index("ix_pms_connections_workspace_active", table_name="pms_connections")
    op.drop_table("pms_connections")
