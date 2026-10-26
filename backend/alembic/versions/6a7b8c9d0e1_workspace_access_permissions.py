"""Add Workspace access requests and granular member permissions.

Revision ID: 6a7b8c9d0e1
Revises: 5f6a7b8c9d0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6a7b8c9d0e1"
down_revision: str | None = "5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

request_status = postgresql.ENUM(
    "PENDING",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
    name="workspace_access_request_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    request_status.create(bind, checkfirst=True)
    op.execute(
        "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS "
        "'WORKSPACE_ACCESS_REQUESTED'"
    )
    op.execute(
        "ALTER TYPE notification_entity_type ADD VALUE IF NOT EXISTS "
        "'WORKSPACE_ACCESS_REQUEST'"
    )

    op.create_table(
        "workspace_join_settings",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("join_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("join_code_hash", sa.String(length=64), nullable=True),
        sa.Column("code_hint", sa.String(length=4), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("join_code_hash"),
    )
    op.create_index(
        "ix_workspace_join_settings_workspace_id",
        "workspace_join_settings",
        ["workspace_id"],
        unique=True,
    )

    op.create_table(
        "workspace_access_requests",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", request_status, nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_access_requests_workspace_id",
        "workspace_access_requests",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_access_requests_user_id",
        "workspace_access_requests",
        ["user_id"],
    )
    op.create_index(
        "uq_workspace_access_request_pending",
        "workspace_access_requests",
        ["workspace_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.create_table(
        "workspace_member_capabilities",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column(
            "granted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("granted_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["workspace_members.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "membership_id", "capability", name="uq_workspace_member_capability"
        ),
    )
    op.create_index(
        "ix_workspace_member_capabilities_workspace_id",
        "workspace_member_capabilities",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_member_capabilities_membership_id",
        "workspace_member_capabilities",
        ["membership_id"],
    )

    op.create_table(
        "workspace_access_audit_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("access_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["access_request_id"],
            ["workspace_access_requests.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_access_audit_events_workspace_id",
        "workspace_access_audit_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_access_audit_events_actor_user_id",
        "workspace_access_audit_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_workspace_access_audit_events_action",
        "workspace_access_audit_events",
        ["action"],
    )


def _restore_notification_enums() -> None:
    op.execute(
        "DELETE FROM notifications WHERE type = 'WORKSPACE_ACCESS_REQUESTED'"
    )
    op.execute("ALTER TABLE notifications ALTER COLUMN type TYPE text USING type::text")
    op.execute("DROP TYPE notification_type")
    op.execute(
        "CREATE TYPE notification_type AS ENUM ("
        "'CONVERSATION_HANDOFF','CONVERSATION_ASSIGNED','NEW_CUSTOMER_MESSAGE',"
        "'ACTION_CREATED','ACTION_ASSIGNED','PAYMENT_VERIFIED',"
        "'PAYMENT_REVIEW_REQUIRED')"
    )
    op.execute(
        "ALTER TABLE notifications ALTER COLUMN type TYPE notification_type "
        "USING type::notification_type"
    )
    op.execute(
        "ALTER TABLE notifications ALTER COLUMN entity_type TYPE text "
        "USING entity_type::text"
    )
    op.execute("DROP TYPE notification_entity_type")
    op.execute(
        "CREATE TYPE notification_entity_type AS ENUM "
        "('CONVERSATION','ACTION','PAYMENT')"
    )
    op.execute(
        "ALTER TABLE notifications ALTER COLUMN entity_type "
        "TYPE notification_entity_type USING entity_type::notification_entity_type"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_access_audit_events_action",
        table_name="workspace_access_audit_events",
    )
    op.drop_index(
        "ix_workspace_access_audit_events_actor_user_id",
        table_name="workspace_access_audit_events",
    )
    op.drop_index(
        "ix_workspace_access_audit_events_workspace_id",
        table_name="workspace_access_audit_events",
    )
    op.drop_table("workspace_access_audit_events")
    op.drop_index(
        "ix_workspace_member_capabilities_membership_id",
        table_name="workspace_member_capabilities",
    )
    op.drop_index(
        "ix_workspace_member_capabilities_workspace_id",
        table_name="workspace_member_capabilities",
    )
    op.drop_table("workspace_member_capabilities")
    op.drop_index(
        "uq_workspace_access_request_pending",
        table_name="workspace_access_requests",
    )
    op.drop_index(
        "ix_workspace_access_requests_user_id",
        table_name="workspace_access_requests",
    )
    op.drop_index(
        "ix_workspace_access_requests_workspace_id",
        table_name="workspace_access_requests",
    )
    op.drop_table("workspace_access_requests")
    op.drop_index(
        "ix_workspace_join_settings_workspace_id",
        table_name="workspace_join_settings",
    )
    op.drop_table("workspace_join_settings")
    request_status.drop(op.get_bind(), checkfirst=True)
    _restore_notification_enums()
