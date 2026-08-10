"""webchat message idempotency

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-10
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            text(
                """
            SELECT conversation_id, external_message_id, count(*) AS duplicate_count
            FROM messages
            WHERE external_message_id IS NOT NULL
            GROUP BY conversation_id, external_message_id
            HAVING count(*) > 1
            LIMIT 1
            """
            )
        )
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(
            "Cannot add WebChat message idempotency constraint: duplicate "
            "(conversation_id, external_message_id) rows exist"
        )
    op.create_unique_constraint(
        "uq_messages_conversation_external_id",
        "messages",
        ["conversation_id", "external_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_messages_conversation_external_id", "messages", type_="unique"
    )
