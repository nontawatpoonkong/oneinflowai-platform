"""promotion discount code and attribution foundation

Revision ID: 9d0e1f2a3b4
Revises: 8c9d0e1f2a3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9d0e1f2a3b4"
down_revision: str | None = "8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_hotel_room_type_workspace_id",
        "hotel_room_types",
        ["workspace_id", "id"],
    )
    op.create_unique_constraint(
        "uq_hotel_rate_plan_workspace_id",
        "hotel_rate_plans",
        ["workspace_id", "id"],
    )
    campaign_status = sa.Enum(
        "DRAFT",
        "ACTIVE",
        "PAUSED",
        "EXPIRED",
        "ARCHIVED",
        name="promotion_campaign_status",
    )
    discount_type = sa.Enum(
        "PERCENTAGE", "FIXED_AMOUNT", name="promotion_discount_type"
    )
    code_status = sa.Enum(
        "ACTIVE",
        "DISABLED",
        "EXHAUSTED",
        "EXPIRED",
        "ARCHIVED",
        name="promotion_code_status",
    )
    promotion_source = sa.Enum(
        "DIRECT",
        "WEBCHAT",
        "LINE",
        "FACEBOOK",
        "INSTAGRAM",
        "PARTNER",
        "MANUAL",
        "OTHER",
        name="promotion_source",
    )
    attribution_source = sa.Enum(
        "DIRECT",
        "WEBCHAT",
        "LINE",
        "FACEBOOK",
        "INSTAGRAM",
        "PARTNER",
        "MANUAL",
        "OTHER",
        name="booking_attribution_source",
    )
    redemption_status = sa.Enum(
        "RESERVED",
        "CONFIRMED",
        "RELEASED",
        name="promotion_redemption_status",
    )

    op.create_table(
        "promotion_campaigns",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("status", campaign_status, nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
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
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_promotion_campaign_validity",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_promotion_campaign_scope"),
    )
    op.create_index(
        "ix_promotion_campaign_workspace_status",
        "promotion_campaigns",
        ["workspace_id", "status", "updated_at"],
    )
    op.create_table(
        "promotions",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("discount_type", discount_type, nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_discount_amount", sa.Numeric(12, 2)),
        sa.Column("minimum_subtotal", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("stay_date_start", sa.Date()),
        sa.Column("stay_date_end", sa.Date()),
        sa.Column("total_usage_limit", sa.Integer()),
        sa.Column("per_customer_limit", sa.Integer()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.CheckConstraint("discount_value > 0", name="ck_promotion_discount_positive"),
        sa.CheckConstraint(
            "discount_type <> 'PERCENTAGE' OR discount_value <= 100",
            name="ck_promotion_percentage_range",
        ),
        sa.CheckConstraint(
            "max_discount_amount IS NULL OR max_discount_amount >= 0",
            name="ck_promotion_max_discount",
        ),
        sa.CheckConstraint(
            "minimum_subtotal IS NULL OR minimum_subtotal >= 0",
            name="ck_promotion_minimum_subtotal",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_promotion_validity",
        ),
        sa.CheckConstraint(
            "stay_date_end IS NULL OR stay_date_start IS NULL OR "
            "stay_date_end >= stay_date_start",
            name="ck_promotion_stay_dates",
        ),
        sa.CheckConstraint(
            "total_usage_limit IS NULL OR total_usage_limit > 0",
            name="ck_promotion_total_usage_limit",
        ),
        sa.CheckConstraint(
            "per_customer_limit IS NULL OR per_customer_limit > 0",
            name="ck_promotion_customer_limit",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["promotion_campaigns.workspace_id", "promotion_campaigns.id"],
            ondelete="RESTRICT",
            name="fk_promotion_campaign_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_promotion_scope"),
    )
    op.create_index(
        "ix_promotion_workspace_campaign", "promotions", ["workspace_id", "campaign_id"]
    )
    op.alter_column("promotions", "active", server_default=None)
    op.create_table(
        "promotion_codes",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("normalized_code", sa.String(32), nullable=False),
        sa.Column("status", code_status, nullable=False),
        sa.Column("usage_limit", sa.Integer()),
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
            "usage_limit IS NULL OR usage_limit > 0",
            name="ck_promotion_code_usage_limit",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="RESTRICT",
            name="fk_promotion_code_promotion_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "normalized_code", name="uq_promotion_code_workspace"
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_promotion_code_scope"),
    )
    op.create_index(
        "ix_promotion_code_lookup",
        "promotion_codes",
        ["workspace_id", "normalized_code"],
    )

    for table, target_table, target_column in (
        ("promotion_properties", "hotel_properties", "property_id"),
        ("promotion_room_types", "hotel_room_types", "room_type_id"),
        ("promotion_rate_plans", "hotel_rate_plans", "rate_plan_id"),
    ):
        op.create_table(
            table,
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(target_column, postgresql.UUID(as_uuid=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["workspace_id", "promotion_id"],
                ["promotions.workspace_id", "promotions.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["workspace_id", target_column],
                [f"{target_table}.workspace_id", f"{target_table}.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("workspace_id", "promotion_id", target_column),
        )
    op.create_table(
        "promotion_sources",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", promotion_source, nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "promotion_id", "source"),
    )

    op.add_column(
        "hotel_bookings",
        sa.Column(
            "discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "hotel_bookings",
        sa.Column("promotion_snapshot", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.drop_constraint("ck_hotel_booking_totals", "hotel_bookings", type_="check")
    op.create_check_constraint(
        "ck_hotel_booking_totals",
        "hotel_bookings",
        "subtotal >= 0 AND discount_amount >= 0 AND "
        "discount_amount <= subtotal AND total_amount = subtotal - discount_amount",
    )
    op.alter_column("hotel_bookings", "discount_amount", server_default=None)

    op.create_table(
        "booking_attributions",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", attribution_source, nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True)),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True)),
        sa.Column("promotion_code_id", postgresql.UUID(as_uuid=True)),
        sa.Column("partner_identifier", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "booking_id"],
            ["hotel_bookings.workspace_id", "hotel_bookings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["promotion_campaigns.workspace_id", "promotion_campaigns.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "promotion_code_id"],
            ["promotion_codes.workspace_id", "promotion_codes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_booking_attribution_booking"),
    )
    op.create_index(
        "ix_booking_attribution_workspace_source",
        "booking_attributions",
        ["workspace_id", "source"],
    )
    op.create_table(
        "promotion_redemptions",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_code_id", postgresql.UUID(as_uuid=True)),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", redemption_status, nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True)),
        sa.Column("redeemed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("discount_amount >= 0", name="ck_redemption_discount"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "booking_id"],
            ["hotel_bookings.workspace_id", "hotel_bookings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "promotion_id"],
            ["promotions.workspace_id", "promotions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "promotion_code_id"],
            ["promotion_codes.workspace_id", "promotion_codes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_promotion_redemption_booking"),
    )
    op.create_index(
        "ix_promotion_redemption_usage",
        "promotion_redemptions",
        ["workspace_id", "promotion_id", "status", "redeemed_at"],
    )
    op.create_index(
        "ix_promotion_redemption_customer",
        "promotion_redemptions",
        ["workspace_id", "promotion_id", "customer_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_promotion_redemption_customer", table_name="promotion_redemptions"
    )
    op.drop_index("ix_promotion_redemption_usage", table_name="promotion_redemptions")
    op.drop_table("promotion_redemptions")
    op.drop_index(
        "ix_booking_attribution_workspace_source", table_name="booking_attributions"
    )
    op.drop_table("booking_attributions")
    op.drop_constraint("ck_hotel_booking_totals", "hotel_bookings", type_="check")
    op.create_check_constraint(
        "ck_hotel_booking_totals",
        "hotel_bookings",
        "subtotal >= 0 AND total_amount >= 0",
    )
    op.drop_column("hotel_bookings", "promotion_snapshot")
    op.drop_column("hotel_bookings", "discount_amount")
    op.drop_table("promotion_sources")
    op.drop_table("promotion_rate_plans")
    op.drop_table("promotion_room_types")
    op.drop_table("promotion_properties")
    op.drop_index("ix_promotion_code_lookup", table_name="promotion_codes")
    op.drop_table("promotion_codes")
    op.drop_index("ix_promotion_workspace_campaign", table_name="promotions")
    op.drop_table("promotions")
    op.drop_index(
        "ix_promotion_campaign_workspace_status", table_name="promotion_campaigns"
    )
    op.drop_table("promotion_campaigns")
    op.drop_constraint(
        "uq_hotel_rate_plan_workspace_id", "hotel_rate_plans", type_="unique"
    )
    op.drop_constraint(
        "uq_hotel_room_type_workspace_id", "hotel_room_types", type_="unique"
    )
    for name in (
        "promotion_redemption_status",
        "booking_attribution_source",
        "promotion_source",
        "promotion_code_status",
        "promotion_discount_type",
        "promotion_campaign_status",
    ):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
