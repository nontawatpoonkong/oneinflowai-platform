"""platform admin console workspace lifecycle

Revision ID: 0e1f2a3b4c5
Revises: 9d0e1f2a3b4
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0e1f2a3b4c5"
down_revision: str | None = "9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.create_check_constraint(
        "ck_workspace_status",
        "workspaces",
        "status IN ('ACTIVE','SUSPENDED')",
    )
    op.create_index(
        "ix_workspaces_status_created", "workspaces", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_workspaces_status_created", table_name="workspaces")
    op.drop_constraint("ck_workspace_status", "workspaces", type_="check")
    op.drop_column("workspaces", "status")
