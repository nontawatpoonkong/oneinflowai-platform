"""Add physical rooms and transactional Stay operations.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

room_status = postgresql.ENUM(
    "AVAILABLE", "OCCUPIED", "OUT_OF_SERVICE", name="hotel_room_operational_status"
)
stay_status = postgresql.ENUM(
    "EXPECTED", "CHECKED_IN", "CHECKED_OUT", "NO_SHOW", name="hotel_stay_status"
)
stay_event_type = postgresql.ENUM(
    "STAY_CREATED",
    "ROOM_ASSIGNED",
    "ROOM_UNASSIGNED",
    "CHECKED_IN",
    "CHECKED_OUT",
    "NO_SHOW",
    name="hotel_stay_event_type",
)


def upgrade() -> None:
    bind = op.get_bind()
    room_status.create(bind, checkfirst=True)
    stay_status.create(bind, checkfirst=True)
    stay_event_type.create(bind, checkfirst=True)
    op.create_table(
        "hotel_rooms",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("floor", sa.String(32)),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "operational_status",
            postgresql.ENUM(name="hotel_room_operational_status", create_type=False),
            server_default="AVAILABLE",
            nullable=False,
        ),
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
            ["workspace_id", "property_id"],
            ["hotel_properties.workspace_id", "hotel_properties.id"],
            name="fk_hotel_room_property_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id"],
            [
                "hotel_room_types.workspace_id",
                "hotel_room_types.property_id",
                "hotel_room_types.id",
            ],
            name="fk_hotel_room_type_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "property_id", "code", name="uq_hotel_room_code"
        ),
        sa.UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_hotel_room_scope"
        ),
    )
    op.create_index(
        "ix_hotel_rooms_workspace_status",
        "hotel_rooms",
        ["workspace_id", "operational_status"],
    )
    op.create_index(
        "ix_hotel_rooms_property_status",
        "hotel_rooms",
        ["property_id", "operational_status"],
    )
    op.create_table(
        "hotel_stays",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "status",
            postgresql.ENUM(name="hotel_stay_status", create_type=False),
            nullable=False,
        ),
        sa.Column("planned_check_in_date", sa.Date(), nullable=False),
        sa.Column("planned_check_out_date", sa.Date(), nullable=False),
        sa.Column("required_room_count", sa.Integer(), nullable=False),
        sa.Column("actual_check_in_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("actual_check_out_at", sa.TIMESTAMP(timezone=True)),
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
        sa.CheckConstraint(
            "planned_check_out_date > planned_check_in_date", name="ck_hotel_stay_dates"
        ),
        sa.CheckConstraint("required_room_count > 0", name="ck_hotel_stay_room_count"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "booking_id"],
            [
                "hotel_bookings.workspace_id",
                "hotel_bookings.property_id",
                "hotel_bookings.id",
            ],
            name="fk_hotel_stay_booking_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            name="fk_hotel_stay_customer_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_hotel_stay_scope"),
        sa.UniqueConstraint(
            "workspace_id",
            "property_id",
            "id",
            name="uq_hotel_stay_property_scope",
        ),
        sa.UniqueConstraint("workspace_id", "booking_id", name="uq_hotel_stay_booking"),
    )
    op.create_index(
        "ix_hotel_stays_workspace_status", "hotel_stays", ["workspace_id", "status"]
    )
    op.create_index(
        "ix_hotel_stays_property_status", "hotel_stays", ["property_id", "status"]
    )
    op.create_index(
        "ix_hotel_stays_customer", "hotel_stays", ["workspace_id", "customer_id"]
    )
    op.create_index(
        "ix_hotel_stays_arrival",
        "hotel_stays",
        ["workspace_id", "planned_check_in_date"],
    )
    op.create_index(
        "ix_hotel_stays_departure",
        "hotel_stays",
        ["workspace_id", "planned_check_out_date"],
    )
    op.create_table(
        "hotel_stay_room_assignments",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stay_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("released_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "stay_id"],
            [
                "hotel_stays.workspace_id",
                "hotel_stays.property_id",
                "hotel_stays.id",
            ],
            name="fk_hotel_stay_assignment_stay_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_id"],
            ["hotel_rooms.workspace_id", "hotel_rooms.property_id", "hotel_rooms.id"],
            name="fk_hotel_stay_assignment_room_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_hotel_room_active_assignment",
        "hotel_stay_room_assignments",
        ["room_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_index(
        "ix_hotel_stay_assignments_active",
        "hotel_stay_room_assignments",
        ["workspace_id", "stay_id"],
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_table(
        "hotel_stay_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stay_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "event_type",
            postgresql.ENUM(name="hotel_stay_event_type", create_type=False),
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
            ["workspace_id", "property_id", "stay_id"],
            [
                "hotel_stays.workspace_id",
                "hotel_stays.property_id",
                "hotel_stays.id",
            ],
            name="fk_hotel_stay_event_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_id"],
            ["hotel_rooms.workspace_id", "hotel_rooms.property_id", "hotel_rooms.id"],
            name="fk_hotel_stay_event_room_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence"),
    )
    op.create_index(
        "ix_hotel_stay_events_booking_id", "hotel_stay_events", ["booking_id"]
    )
    op.create_index(
        "ix_hotel_stay_events_stay_sequence",
        "hotel_stay_events",
        ["stay_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_hotel_stay_events_stay_sequence", table_name="hotel_stay_events")
    op.drop_index("ix_hotel_stay_events_booking_id", table_name="hotel_stay_events")
    op.drop_table("hotel_stay_events")
    op.drop_index(
        "ix_hotel_stay_assignments_active", table_name="hotel_stay_room_assignments"
    )
    op.drop_index(
        "uq_hotel_room_active_assignment", table_name="hotel_stay_room_assignments"
    )
    op.drop_table("hotel_stay_room_assignments")
    op.drop_index("ix_hotel_stays_departure", table_name="hotel_stays")
    op.drop_index("ix_hotel_stays_arrival", table_name="hotel_stays")
    op.drop_index("ix_hotel_stays_customer", table_name="hotel_stays")
    op.drop_index("ix_hotel_stays_property_status", table_name="hotel_stays")
    op.drop_index("ix_hotel_stays_workspace_status", table_name="hotel_stays")
    op.drop_table("hotel_stays")
    op.drop_index("ix_hotel_rooms_property_status", table_name="hotel_rooms")
    op.drop_index("ix_hotel_rooms_workspace_status", table_name="hotel_rooms")
    op.drop_table("hotel_rooms")
    stay_event_type.drop(op.get_bind(), checkfirst=True)
    stay_status.drop(op.get_bind(), checkfirst=True)
    room_status.drop(op.get_bind(), checkfirst=True)
