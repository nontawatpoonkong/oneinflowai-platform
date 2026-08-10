"""action fulfillment queue

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    execution_mode = sa.Enum("MANUAL", "AUTOMATED", name="action_execution_mode")
    request_status = sa.Enum(
        "WAITING",
        "ASSIGNED",
        "IN_PROGRESS",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        name="action_request_status",
    )
    priority = sa.Enum("LOW", "NORMAL", "HIGH", "URGENT", name="action_priority")
    actor = sa.Enum("AI", "HUMAN", "SYSTEM", name="action_actor_type")
    event_actor = sa.Enum("AI", "HUMAN", "SYSTEM", name="action_event_actor_type")
    event_type = sa.Enum(
        "CREATED",
        "ASSIGNED",
        "STARTED",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        name="action_event_type",
    )
    op.create_table(
        "action_definitions",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("execution_mode", execution_mode, nullable=False),
        sa.Column("required_fields", postgresql.JSONB(), nullable=False),
        sa.Column("optional_fields", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.UniqueConstraint(
            "workspace_id", "key", name="uq_action_definition_workspace_key"
        ),
    )
    op.create_index(
        "ix_action_definitions_workspace_id", "action_definitions", ["workspace_id"]
    )
    op.create_table(
        "action_requests",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_definitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
        ),
        sa.Column("status", request_status, nullable=False),
        sa.Column("priority", priority, nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_type", actor, nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "assigned_to_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("assigned_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_action_request_workspace_idempotency",
        ),
    )
    for column in (
        "workspace_id",
        "action_definition_id",
        "conversation_id",
        "customer_id",
        "assigned_to_user_id",
    ):
        op.create_index(f"ix_action_requests_{column}", "action_requests", [column])
    op.create_index(
        "ix_action_requests_queue",
        "action_requests",
        ["workspace_id", "status", "created_at"],
    )
    op.create_table(
        "action_events",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_requests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("actor_type", event_actor, nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_action_events_workspace_id", "action_events", ["workspace_id"])
    op.create_index(
        "ix_action_events_action_request_id", "action_events", ["action_request_id"]
    )
    op.create_index(
        "ix_action_events_request_created",
        "action_events",
        ["action_request_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("action_events")
    op.drop_table("action_requests")
    op.drop_table("action_definitions")
    for name in (
        "action_event_type",
        "action_event_actor_type",
        "action_actor_type",
        "action_priority",
        "action_request_status",
        "action_execution_mode",
    ):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
