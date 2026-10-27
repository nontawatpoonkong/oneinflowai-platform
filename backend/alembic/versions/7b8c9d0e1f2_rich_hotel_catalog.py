"""rich hotel catalog and availability metadata

Revision ID: 7b8c9d0e1f2
Revises: 6a7b8c9d0e1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7b8c9d0e1f2"
down_revision: str | None = "6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hotel_room_types", sa.Column("short_description", sa.String(500)))
    op.add_column("hotel_room_types", sa.Column("room_size_sqm", sa.Numeric(7, 2)))
    op.add_column(
        "hotel_room_types",
        sa.Column(
            "smoking_policy",
            sa.String(24),
            nullable=False,
            server_default="NON_SMOKING",
        ),
    )
    op.add_column(
        "hotel_room_types",
        sa.Column(
            "accessibility_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("hotel_room_types", sa.Column("public_highlights", sa.Text()))
    op.add_column(
        "hotel_room_types",
        sa.Column(
            "view_type", sa.String(24), nullable=False, server_default="NO_SPECIAL_VIEW"
        ),
    )
    op.add_column("hotel_room_types", sa.Column("custom_view_label", sa.String(120)))
    op.create_check_constraint(
        "ck_hotel_room_type_size",
        "hotel_room_types",
        "room_size_sqm IS NULL OR room_size_sqm > 0",
    )
    op.create_check_constraint(
        "ck_hotel_room_type_view",
        "hotel_room_types",
        "view_type IN ('CITY','GARDEN','POOL','MOUNTAIN','SEA','RIVER',"
        "'COURTYARD','NO_SPECIAL_VIEW','CUSTOM')",
    )
    op.create_check_constraint(
        "ck_hotel_room_type_smoking",
        "hotel_room_types",
        "smoking_policy IN ('NON_SMOKING','SMOKING_ALLOWED','DESIGNATED_ONLY')",
    )

    op.add_column("hotel_rooms", sa.Column("building", sa.String(80)))
    op.add_column("hotel_rooms", sa.Column("wing", sa.String(80)))
    op.add_column("hotel_rooms", sa.Column("internal_notes", sa.String(1000)))

    op.create_table(
        "hotel_amenity_definitions",
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("default_name_en", sa.String(160), nullable=False),
        sa.Column("default_name_th", sa.String(160), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "value_type IN ('BOOLEAN','NUMBER','TEXT')",
            name="ck_hotel_amenity_value_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_hotel_amenity_code"),
    )
    op.create_index(
        "ix_hotel_amenity_definitions_category",
        "hotel_amenity_definitions",
        ["category"],
    )

    op.create_table(
        "hotel_room_type_beds",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bed_type", sa.String(24), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("custom_label", sa.String(120)),
        sa.Column("width_cm", sa.Integer()),
        sa.Column("length_cm", sa.Integer()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_room_type_bed_quantity"),
        sa.CheckConstraint(
            "width_cm IS NULL OR width_cm > 0", name="ck_room_type_bed_width"
        ),
        sa.CheckConstraint(
            "length_cm IS NULL OR length_cm > 0", name="ck_room_type_bed_length"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["room_type_id"], ["hotel_room_types.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_type_id", "sort_order", name="uq_room_type_bed_order"
        ),
    )
    op.create_index(
        "ix_hotel_room_type_beds_workspace_id", "hotel_room_type_beds", ["workspace_id"]
    )
    op.create_index(
        "ix_hotel_room_type_beds_room_type_id", "hotel_room_type_beds", ["room_type_id"]
    )

    op.create_table(
        "hotel_room_type_amenities",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "amenity_definition_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("boolean_value", sa.Boolean()),
        sa.Column("number_value", sa.Numeric(10, 2)),
        sa.Column("text_value", sa.Text()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "num_nonnulls(boolean_value, number_value, text_value) = 1",
            name="ck_room_type_amenity_one_value",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["room_type_id"], ["hotel_room_types.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["amenity_definition_id"],
            ["hotel_amenity_definitions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_type_id", "amenity_definition_id", name="uq_room_type_amenity"
        ),
    )
    op.create_index(
        "ix_hotel_room_type_amenities_workspace_id",
        "hotel_room_type_amenities",
        ["workspace_id"],
    )
    op.create_index(
        "ix_hotel_room_type_amenities_room_type_id",
        "hotel_room_type_amenities",
        ["room_type_id"],
    )

    op.create_table(
        "hotel_room_type_images",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("public_url", sa.String(1000)),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("caption", sa.String(300)),
        sa.Column("alt_text", sa.String(300), nullable=False),
        sa.Column("image_category", sa.String(24), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_cover", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["room_type_id"], ["hotel_room_types.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_room_type_image_storage_key"),
        sa.UniqueConstraint(
            "room_type_id", "sort_order", name="uq_room_type_image_order"
        ),
    )
    op.create_index(
        "ix_hotel_room_type_images_workspace_id",
        "hotel_room_type_images",
        ["workspace_id"],
    )
    op.create_index(
        "ix_hotel_room_type_images_room_type_id",
        "hotel_room_type_images",
        ["room_type_id"],
    )
    op.create_index(
        "uq_room_type_image_cover",
        "hotel_room_type_images",
        ["room_type_id"],
        unique=True,
        postgresql_where=sa.text("is_cover"),
    )


def downgrade() -> None:
    op.drop_index("uq_room_type_image_cover", table_name="hotel_room_type_images")
    op.drop_index(
        "ix_hotel_room_type_images_room_type_id", table_name="hotel_room_type_images"
    )
    op.drop_index(
        "ix_hotel_room_type_images_workspace_id", table_name="hotel_room_type_images"
    )
    op.drop_table("hotel_room_type_images")
    op.drop_index(
        "ix_hotel_room_type_amenities_room_type_id",
        table_name="hotel_room_type_amenities",
    )
    op.drop_index(
        "ix_hotel_room_type_amenities_workspace_id",
        table_name="hotel_room_type_amenities",
    )
    op.drop_table("hotel_room_type_amenities")
    op.drop_index(
        "ix_hotel_room_type_beds_room_type_id", table_name="hotel_room_type_beds"
    )
    op.drop_index(
        "ix_hotel_room_type_beds_workspace_id", table_name="hotel_room_type_beds"
    )
    op.drop_table("hotel_room_type_beds")
    op.drop_index(
        "ix_hotel_amenity_definitions_category", table_name="hotel_amenity_definitions"
    )
    op.drop_table("hotel_amenity_definitions")
    op.drop_column("hotel_rooms", "internal_notes")
    op.drop_column("hotel_rooms", "wing")
    op.drop_column("hotel_rooms", "building")
    op.drop_constraint("ck_hotel_room_type_smoking", "hotel_room_types", type_="check")
    op.drop_constraint("ck_hotel_room_type_view", "hotel_room_types", type_="check")
    op.drop_constraint("ck_hotel_room_type_size", "hotel_room_types", type_="check")
    op.drop_column("hotel_room_types", "custom_view_label")
    op.drop_column("hotel_room_types", "view_type")
    op.drop_column("hotel_room_types", "public_highlights")
    op.drop_column("hotel_room_types", "accessibility_available")
    op.drop_column("hotel_room_types", "smoking_policy")
    op.drop_column("hotel_room_types", "room_size_sqm")
    op.drop_column("hotel_room_types", "short_description")
