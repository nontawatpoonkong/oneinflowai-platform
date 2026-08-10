"""action collection sessions

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_collection_sessions",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("action_definition_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("action_request_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "COLLECTING",
                "AWAITING_CONFIRMATION",
                "CONFIRMED",
                "CANCELLED",
                "EXPIRED",
                name="action_collection_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "collected_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "missing_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "invalid_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("confirmation_token_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "confirmation_expires_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column("action_idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_by_type",
            sa.Enum("AI", "HUMAN", "SYSTEM", name="action_collection_actor_type"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["action_definition_id"], ["action_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["action_request_id"], ["action_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_idempotency_key", name="uq_action_collection_idempotency_key"
        ),
    )
    op.create_index(
        "ix_action_collection_conversation",
        "action_collection_sessions",
        ["conversation_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_action_collection_workspace_status",
        "action_collection_sessions",
        ["workspace_id", "status"],
        unique=False,
    )
    for column in (
        "action_definition_id",
        "action_request_id",
        "conversation_id",
        "customer_id",
        "workspace_id",
    ):
        op.create_index(
            f"ix_action_collection_sessions_{column}",
            "action_collection_sessions",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "workspace_id",
        "customer_id",
        "conversation_id",
        "action_request_id",
        "action_definition_id",
    ):
        op.drop_index(
            f"ix_action_collection_sessions_{column}",
            table_name="action_collection_sessions",
        )
    op.drop_index(
        "ix_action_collection_workspace_status",
        table_name="action_collection_sessions",
    )
    op.drop_index(
        "ix_action_collection_conversation",
        table_name="action_collection_sessions",
    )
    op.drop_table("action_collection_sessions")
    sa.Enum(name="action_collection_actor_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="action_collection_status").drop(op.get_bind(), checkfirst=True)
