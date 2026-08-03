"""email verification foundation

Revision ID: c7d2e4f6a8b0
Revises: b8a1d2e3f4c5
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d2e4f6a8b0"
down_revision: str | None = "b8a1d2e3f4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.alter_column("users", "email_verified", server_default=sa.false())

    purpose = sa.Enum(
        "email_verification",
        "password_reset",
        "workspace_invite",
        "login_2fa",
        name="verification_purpose",
    )
    op.create_table(
        "verification_challenges",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("purpose", purpose, nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "failed_attempts", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "resend_available_at", sa.TIMESTAMP(timezone=True), nullable=False
        ),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_verification_challenges_user_id",
        "verification_challenges",
        ["user_id"],
    )
    op.create_index(
        "ix_verification_challenges_expires_at",
        "verification_challenges",
        ["expires_at"],
    )
    op.create_index(
        "ix_verification_challenges_user_purpose_created",
        "verification_challenges",
        ["user_id", "purpose", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verification_challenges_user_purpose_created",
        table_name="verification_challenges",
    )
    op.drop_index(
        "ix_verification_challenges_expires_at",
        table_name="verification_challenges",
    )
    op.drop_index(
        "ix_verification_challenges_user_id",
        table_name="verification_challenges",
    )
    op.drop_table("verification_challenges")
    sa.Enum(name="verification_purpose").drop(op.get_bind(), checkfirst=True)
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
