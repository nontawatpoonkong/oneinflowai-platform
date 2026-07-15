"""conversation ai mode

Revision ID: a7f0c1d2e3b4
Revises: 1e15c6633941
Create Date: 2026-07-14 10:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7f0c1d2e3b4"
down_revision: str | None = "1e15c6633941"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

conversation_mode = sa.Enum("AUTO", "COPILOT", "HUMAN", name="conversation_mode")


def upgrade() -> None:
    bind = op.get_bind()
    conversation_mode.create(bind, checkfirst=True)

    # Existing rows default to AUTO, so no data is lost.
    op.add_column(
        "conversations",
        sa.Column(
            "ai_mode",
            conversation_mode,
            nullable=False,
            server_default="AUTO",
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("taken_over_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("taken_over_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_taken_over_by_users",
        "conversations",
        "users",
        ["taken_over_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_conversations_taken_over_by_users",
        "conversations",
        type_="foreignkey",
    )
    op.drop_column("conversations", "taken_over_at")
    op.drop_column("conversations", "taken_over_by")
    op.drop_column("conversations", "ai_mode")
    conversation_mode.drop(op.get_bind(), checkfirst=True)
