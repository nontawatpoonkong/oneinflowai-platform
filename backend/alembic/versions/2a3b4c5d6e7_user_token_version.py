"""users.token_version: per-user access token revocation

Revision ID: 2a3b4c5d6e7
Revises: 1f2a3b4c5d6
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2a3b4c5d6e7"
down_revision: str | None = "1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive: existing users start at version 0. Tokens issued before this
    # deploy carry no `ver` claim and are refused, so users sign in once.
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
