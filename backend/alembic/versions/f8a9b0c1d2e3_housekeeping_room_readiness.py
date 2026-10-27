"""Add room readiness and housekeeping lifecycle.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

readiness = postgresql.ENUM(
    "READY", "DIRTY", "CLEANING", name="hotel_room_readiness_status"
)
task_status = postgresql.ENUM(
    "PENDING",
    "IN_PROGRESS",
    "COMPLETED",
    "CANCELLED",
    name="hotel_housekeeping_task_status",
)
priority = postgresql.ENUM("LOW", "NORMAL", "HIGH", name="hotel_housekeeping_priority")
event_type = postgresql.ENUM(
    "ROOM_DIRTY",
    "HOUSEKEEPING_TASK_CREATED",
    "HOUSEKEEPING_ASSIGNED",
    "HOUSEKEEPING_STARTED",
    "HOUSEKEEPING_COMPLETED",
    "ROOM_READY",
    "HOUSEKEEPING_CANCELLED",
    name="hotel_housekeeping_event_type",
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (readiness, task_status, priority, event_type):
        enum.create(bind, checkfirst=True)
    op.add_column(
        "hotel_rooms",
        sa.Column(
            "readiness_status",
            postgresql.ENUM(name="hotel_room_readiness_status", create_type=False),
            server_default="READY",
            nullable=False,
        ),
    )
    op.create_table(
        "hotel_housekeeping_tasks",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stay_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "status",
            postgresql.ENUM(name="hotel_housekeeping_task_status", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "priority",
            postgresql.ENUM(name="hotel_housekeeping_priority", create_type=False),
            nullable=False,
        ),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
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
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_id"],
            ["hotel_rooms.workspace_id", "hotel_rooms.property_id", "hotel_rooms.id"],
            name="fk_housekeeping_task_room_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "stay_id"],
            ["hotel_stays.workspace_id", "hotel_stays.property_id", "hotel_stays.id"],
            name="fk_housekeeping_task_stay_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "stay_id",
            "room_id",
            "source",
            name="uq_housekeeping_checkout_task",
        ),
        sa.UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_housekeeping_task_scope"
        ),
    )
    op.create_index(
        "uq_housekeeping_active_room",
        "hotel_housekeeping_tasks",
        ["room_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'IN_PROGRESS')"),
    )
    op.create_index(
        "ix_housekeeping_workspace_status",
        "hotel_housekeeping_tasks",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_housekeeping_property_status",
        "hotel_housekeeping_tasks",
        ["property_id", "status"],
    )
    op.create_index(
        "ix_housekeeping_assignee_status",
        "hotel_housekeeping_tasks",
        ["assigned_to_user_id", "status"],
    )
    op.create_table(
        "hotel_housekeeping_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM(name="hotel_housekeeping_event_type", create_type=False),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            ["workspace_id", "property_id", "task_id"],
            [
                "hotel_housekeeping_tasks.workspace_id",
                "hotel_housekeeping_tasks.property_id",
                "hotel_housekeeping_tasks.id",
            ],
            name="fk_housekeeping_event_task_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence"),
    )
    op.create_index(
        "ix_housekeeping_events_task_sequence",
        "hotel_housekeeping_events",
        ["task_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_housekeeping_events_task_sequence", table_name="hotel_housekeeping_events"
    )
    op.drop_table("hotel_housekeeping_events")
    op.drop_index(
        "ix_housekeeping_assignee_status", table_name="hotel_housekeeping_tasks"
    )
    op.drop_index(
        "ix_housekeeping_property_status", table_name="hotel_housekeeping_tasks"
    )
    op.drop_index(
        "ix_housekeeping_workspace_status", table_name="hotel_housekeeping_tasks"
    )
    op.drop_index("uq_housekeeping_active_room", table_name="hotel_housekeeping_tasks")
    op.drop_table("hotel_housekeeping_tasks")
    op.drop_column("hotel_rooms", "readiness_status")
    for enum in (event_type, priority, task_status, readiness):
        enum.drop(op.get_bind(), checkfirst=True)
