"""human handoff, read state, and notifications

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

handoff_reason = postgresql.ENUM(
    "CUSTOMER_REQUEST",
    "AI_UNCERTAIN",
    "GROUNDING_FAILURE",
    "ACTION_REQUIRES_HUMAN",
    "PAYMENT_REVIEW",
    "MANUAL_ADMIN",
    "OTHER",
    name="handoff_reason",
    create_type=False,
)
notification_type = postgresql.ENUM(
    "CONVERSATION_HANDOFF",
    "CONVERSATION_ASSIGNED",
    "NEW_CUSTOMER_MESSAGE",
    "ACTION_CREATED",
    "ACTION_ASSIGNED",
    "PAYMENT_VERIFIED",
    "PAYMENT_REVIEW_REQUIRED",
    name="notification_type",
    create_type=False,
)
notification_entity_type = postgresql.ENUM(
    "CONVERSATION",
    "ACTION",
    "PAYMENT",
    name="notification_entity_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    handoff_reason.create(bind, checkfirst=True)
    notification_type.create(bind, checkfirst=True)
    notification_entity_type.create(bind, checkfirst=True)
    op.add_column(
        "conversations", sa.Column("handoff_reason", handoff_reason, nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("handoff_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "needs_attention",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_table(
        "conversation_read_states",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_message_id", sa.Uuid(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["last_read_message_id"], ["messages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "user_id", name="uq_conversation_read_state_user"
        ),
    )
    for column in ("workspace_id", "conversation_id", "user_id"):
        op.create_index(
            f"ix_conversation_read_states_{column}",
            "conversation_read_states",
            [column],
        )
    op.create_table(
        "notifications",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("type", notification_type, nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.String(320), nullable=False),
        sa.Column("entity_type", notification_entity_type, nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deduplication_key", sa.String(255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "recipient_user_id",
            "deduplication_key",
            name="uq_notification_recipient_deduplication",
        ),
    )
    for column in ("workspace_id", "recipient_user_id", "entity_id"):
        op.create_index(f"ix_notifications_{column}", "notifications", [column])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("conversation_read_states")
    for column in (
        "needs_attention",
        "assigned_at",
        "handoff_requested_at",
        "handoff_reason",
    ):
        op.drop_column("conversations", column)
    bind = op.get_bind()
    notification_entity_type.drop(bind, checkfirst=True)
    notification_type.drop(bind, checkfirst=True)
    handoff_reason.drop(bind, checkfirst=True)
