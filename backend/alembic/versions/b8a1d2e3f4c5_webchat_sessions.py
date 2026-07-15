"""webchat sessions

Revision ID: b8a1d2e3f4c5
Revises: a7f0c1d2e3b4
Create Date: 2026-07-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8a1d2e3f4c5"
down_revision: str | None = "a7f0c1d2e3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webchat_sessions",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("landing_url", sa.String(length=2048), nullable=True),
        sa.Column("referrer", sa.String(length=2048), nullable=True),
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
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webchat_sessions_conversation_id",
        "webchat_sessions",
        ["conversation_id"],
        unique=True,
    )
    op.create_index(
        "ix_webchat_sessions_expires_at", "webchat_sessions", ["expires_at"]
    )
    op.create_index("ix_webchat_sessions_ip_hash", "webchat_sessions", ["ip_hash"])
    op.create_index(
        "ix_webchat_sessions_token_hash",
        "webchat_sessions",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_webchat_sessions_token_hash", table_name="webchat_sessions")
    op.drop_index("ix_webchat_sessions_ip_hash", table_name="webchat_sessions")
    op.drop_index("ix_webchat_sessions_expires_at", table_name="webchat_sessions")
    op.drop_index("ix_webchat_sessions_conversation_id", table_name="webchat_sessions")
    op.drop_table("webchat_sessions")
