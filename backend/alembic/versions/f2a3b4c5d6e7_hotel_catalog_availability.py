"""Add authoritative Hotel catalog and daily inventory.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hotel_properties",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("check_in_time", sa.Time(), nullable=True),
        sa.Column("check_out_time", sa.Time(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_hotel_property_workspace_id"
        ),
    )
    op.create_index(
        "ix_hotel_properties_workspace_id", "hotel_properties", ["workspace_id"]
    )

    op.create_table(
        "hotel_room_types",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("max_adults", sa.Integer(), nullable=False),
        sa.Column("max_children", sa.Integer(), nullable=False),
        sa.Column("max_occupancy", sa.Integer(), nullable=False),
        sa.Column("base_capacity", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.CheckConstraint("max_adults > 0", name="ck_hotel_room_type_adults"),
        sa.CheckConstraint("max_children >= 0", name="ck_hotel_room_type_children"),
        sa.CheckConstraint("max_occupancy > 0", name="ck_hotel_room_type_occupancy"),
        sa.CheckConstraint("base_capacity > 0", name="ck_hotel_room_type_capacity"),
        sa.CheckConstraint(
            "max_occupancy >= max_adults", name="ck_hotel_room_type_occupancy_adults"
        ),
        sa.CheckConstraint(
            "base_capacity <= max_occupancy", name="ck_hotel_room_type_base_capacity"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id"],
            ["hotel_properties.workspace_id", "hotel_properties.id"],
            name="fk_hotel_room_type_property_workspace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "code", name="uq_hotel_room_type_code"),
        sa.UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_hotel_room_type_scope"
        ),
    )
    op.create_index(
        "ix_hotel_room_types_workspace_id", "hotel_room_types", ["workspace_id"]
    )
    op.create_index(
        "ix_hotel_room_types_property_id", "hotel_room_types", ["property_id"]
    )

    op.create_table(
        "hotel_rate_plans",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("base_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("refundable", sa.Boolean(), nullable=False),
        sa.Column("cancellation_policy_summary", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.CheckConstraint("base_price >= 0", name="ck_hotel_rate_plan_base_price"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id"],
            [
                "hotel_room_types.workspace_id",
                "hotel_room_types.property_id",
                "hotel_room_types.id",
            ],
            name="fk_hotel_rate_plan_room_type_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_type_id", "code", name="uq_hotel_rate_plan_code"),
    )
    op.create_index(
        "ix_hotel_rate_plans_workspace_id", "hotel_rate_plans", ["workspace_id"]
    )
    op.create_index(
        "ix_hotel_rate_plans_property_id", "hotel_rate_plans", ["property_id"]
    )
    op.create_index(
        "ix_hotel_rate_plans_room_type_id", "hotel_rate_plans", ["room_type_id"]
    )

    op.create_table(
        "hotel_inventory_dates",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_date", sa.Date(), nullable=False),
        sa.Column("total_units", sa.Integer(), nullable=False),
        sa.Column("reserved_units", sa.Integer(), nullable=False),
        sa.Column("blocked_units", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("total_units >= 0", name="ck_hotel_inventory_total"),
        sa.CheckConstraint("reserved_units >= 0", name="ck_hotel_inventory_reserved"),
        sa.CheckConstraint("blocked_units >= 0", name="ck_hotel_inventory_blocked"),
        sa.CheckConstraint(
            "reserved_units + blocked_units <= total_units",
            name="ck_hotel_inventory_capacity",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id"],
            [
                "hotel_room_types.workspace_id",
                "hotel_room_types.property_id",
                "hotel_room_types.id",
            ],
            name="fk_hotel_inventory_room_type_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_type_id", "inventory_date", name="uq_hotel_inventory_room_date"
        ),
    )
    op.create_index(
        "ix_hotel_inventory_dates_workspace_id",
        "hotel_inventory_dates",
        ["workspace_id"],
    )
    op.create_index(
        "ix_hotel_inventory_dates_property_id", "hotel_inventory_dates", ["property_id"]
    )
    op.create_index(
        "ix_hotel_inventory_dates_room_type_id",
        "hotel_inventory_dates",
        ["room_type_id"],
    )
    op.create_index(
        "ix_hotel_inventory_dates_inventory_date",
        "hotel_inventory_dates",
        ["inventory_date"],
    )


def downgrade() -> None:
    op.drop_table("hotel_inventory_dates")
    op.drop_table("hotel_rate_plans")
    op.drop_table("hotel_room_types")
    op.drop_table("hotel_properties")
