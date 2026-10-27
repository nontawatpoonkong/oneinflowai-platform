"""Add immutable room-readiness override audit events.

Revision ID: 0a1b2c3d4e5f
Revises: f8a9b0c1d2e3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0a1b2c3d4e5f"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hotel_room_readiness_override_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("previous_readiness", sa.String(16), nullable=False),
        sa.Column("new_readiness", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "sequence", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_id"],
            ["hotel_rooms.workspace_id", "hotel_rooms.property_id", "hotel_rooms.id"],
            name="fk_readiness_override_room_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence"),
    )
    op.create_index(
        "ix_readiness_override_workspace_room_sequence",
        "hotel_room_readiness_override_events",
        ["workspace_id", "room_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_readiness_override_workspace_room_sequence",
        table_name="hotel_room_readiness_override_events",
    )
    op.drop_table("hotel_room_readiness_override_events")
