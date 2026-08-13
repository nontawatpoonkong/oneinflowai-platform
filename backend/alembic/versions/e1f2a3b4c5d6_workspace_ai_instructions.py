"""Add Workspace-scoped AI instructions.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("ai_instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "ai_instructions")
