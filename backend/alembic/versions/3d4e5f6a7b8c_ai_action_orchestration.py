"""Add bounded AI action orchestration state and audit.

Revision ID: 3d4e5f6a7b8c
Revises: 2c3d4e5f6a7b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3d4e5f6a7b8c"
down_revision: str | None = "2c3d4e5f6a7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


tool_classification = postgresql.ENUM(
    "READ_ONLY",
    "MUTATING_REVERSIBLE",
    "MUTATING_SENSITIVE",
    name="ai_tool_classification",
    create_type=False,
)
tool_status = postgresql.ENUM(
    "PROPOSED",
    "AWAITING_CONFIRMATION",
    "EXECUTING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
    name="ai_tool_action_status",
    create_type=False,
)
audit_event_type = postgresql.ENUM(
    "PROPOSED",
    "CONFIRMED",
    "EXECUTED",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
    name="ai_tool_audit_event_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    tool_classification.create(bind, checkfirst=True)
    tool_status.create(bind, checkfirst=True)
    audit_event_type.create(bind, checkfirst=True)
    op.create_table(
        "ai_tool_actions",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("tool_version", sa.String(16), nullable=False),
        sa.Column("classification", tool_classification, nullable=False),
        sa.Column("status", tool_status, nullable=False),
        sa.Column("validated_args", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("confirmation_token_hash", sa.String(64)),
        sa.Column("confirmation_expires_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("result_reference_type", sa.String(32)),
        sa.Column("result_reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
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
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_ai_tool_action_conversation_scope",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="RESTRICT",
            name="fk_ai_tool_action_customer_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_ai_tool_action_idempotency"
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_ai_tool_action_scope"),
    )
    op.create_index(
        "ix_ai_tool_action_conversation_status",
        "ai_tool_actions",
        ["workspace_id", "conversation_id", "status", "created_at"],
    )
    op.create_table(
        "ai_tool_audit_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", audit_event_type, nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("tool_version", sa.String(16), nullable=False),
        sa.Column("result_status", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "action_id"],
            ["ai_tool_actions.workspace_id", "ai_tool_actions.id"],
            ondelete="CASCADE",
            name="fk_ai_tool_audit_action_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_tool_audit_action_created",
        "ai_tool_audit_events",
        ["action_id", "created_at"],
    )
    op.create_table(
        "ai_conversation_states",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selected_property_id", postgresql.UUID(as_uuid=True)),
        sa.Column("selected_room_type_id", postgresql.UUID(as_uuid=True)),
        sa.Column("selected_rate_plan_id", postgresql.UUID(as_uuid=True)),
        sa.Column("requested_check_in", sa.Date()),
        sa.Column("requested_check_out", sa.Date()),
        sa.Column("adults", sa.Integer()),
        sa.Column("children", sa.Integer()),
        sa.Column("quantity", sa.Integer()),
        sa.Column("active_booking_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "last_availability_options",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
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
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_ai_conversation_state_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "conversation_id", name="uq_ai_conversation_state"
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_conversation_states")
    op.drop_index("ix_ai_tool_audit_action_created", table_name="ai_tool_audit_events")
    op.drop_table("ai_tool_audit_events")
    op.drop_index("ix_ai_tool_action_conversation_status", table_name="ai_tool_actions")
    op.drop_table("ai_tool_actions")
    bind = op.get_bind()
    audit_event_type.drop(bind, checkfirst=True)
    tool_status.drop(bind, checkfirst=True)
    tool_classification.drop(bind, checkfirst=True)
