"""password reset sessions

Revision ID: d8e3f4a5b6c7
Revises: c7d2e4f6a8b0
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e3f4a5b6c7"
down_revision: str | None = "c7d2e4f6a8b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("challenge_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
            ["challenge_id"],
            ["verification_challenges.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_reset_sessions_user_id",
        "password_reset_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_password_reset_sessions_token_hash",
        "password_reset_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_password_reset_sessions_expires_at",
        "password_reset_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_sessions_expires_at",
        table_name="password_reset_sessions",
    )
    op.drop_index(
        "ix_password_reset_sessions_token_hash",
        table_name="password_reset_sessions",
    )
    op.drop_index(
        "ix_password_reset_sessions_user_id",
        table_name="password_reset_sessions",
    )
    op.drop_table("password_reset_sessions")
