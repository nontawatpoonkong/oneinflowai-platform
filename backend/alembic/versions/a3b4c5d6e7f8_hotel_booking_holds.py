"""Add transactional Hotel booking holds and lifecycle events.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

booking_status = sa.Enum(
    "DRAFT",
    "HELD",
    "PENDING_PAYMENT",
    "CONFIRMED",
    "CANCELLED",
    "EXPIRED",
    name="hotel_booking_status",
)
booking_event_type = sa.Enum(
    "BOOKING_CREATED",
    "HOLD_CREATED",
    "HOLD_EXPIRED",
    "BOOKING_CANCELLED",
    "PENDING_PAYMENT_STARTED",
    name="hotel_booking_event_type",
)


def _uuid(name: str, *, nullable: bool = False):
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamps():
    return (
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
    )


def upgrade() -> None:
    # These candidate keys let PostgreSQL enforce the tenant boundary even if
    # a future caller forgets to perform the matching service-level lookup.
    op.create_unique_constraint(
        "uq_customer_workspace_id", "customers", ["workspace_id", "id"]
    )
    op.create_unique_constraint(
        "uq_conversation_workspace_id", "conversations", ["workspace_id", "id"]
    )
    op.create_unique_constraint(
        "uq_hotel_rate_plan_scope",
        "hotel_rate_plans",
        ["workspace_id", "property_id", "room_type_id", "id"],
    )

    op.create_table(
        "hotel_bookings",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("property_id"),
        _uuid("customer_id", nullable=True),
        _uuid("conversation_id", nullable=True),
        sa.Column("guest_name", sa.String(255)),
        sa.Column("status", booking_status, nullable=False),
        sa.Column("check_in", sa.Date(), nullable=False),
        sa.Column("check_out", sa.Date(), nullable=False),
        sa.Column("adults", sa.Integer(), nullable=False),
        sa.Column("children", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("hold_expires_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("property_name_snapshot", sa.String(255), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id"],
            ["hotel_properties.workspace_id", "hotel_properties.id"],
            ondelete="RESTRICT",
            name="fk_hotel_booking_property_scope",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="RESTRICT",
            name="fk_hotel_booking_customer_scope",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="RESTRICT",
            name="fk_hotel_booking_conversation_scope",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_hotel_booking_scope"),
        sa.UniqueConstraint(
            "workspace_id", "property_id", "id", name="uq_hotel_booking_property_scope"
        ),
        sa.UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_hotel_booking_idempotency"
        ),
        sa.CheckConstraint("check_out > check_in", name="ck_hotel_booking_stay"),
        sa.CheckConstraint(
            "adults > 0 AND children >= 0", name="ck_hotel_booking_occupancy"
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND total_amount >= 0", name="ck_hotel_booking_totals"
        ),
    )
    op.create_index("ix_hotel_bookings_property_id", "hotel_bookings", ["property_id"])
    op.create_index("ix_hotel_bookings_customer_id", "hotel_bookings", ["customer_id"])
    op.create_index(
        "ix_hotel_bookings_conversation_id", "hotel_bookings", ["conversation_id"]
    )
    op.create_index(
        "ix_hotel_bookings_workspace_status",
        "hotel_bookings",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_hotel_bookings_hold_expiry", "hotel_bookings", ["hold_expires_at"]
    )

    op.create_table(
        "hotel_booking_items",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("property_id"),
        _uuid("booking_id"),
        _uuid("room_type_id"),
        _uuid("rate_plan_id"),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("nightly_rates", postgresql.JSONB(), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("occupancy_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("rate_policy_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("room_type_name_snapshot", sa.String(255), nullable=False),
        sa.Column("rate_plan_name_snapshot", sa.String(255), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "booking_id"],
            [
                "hotel_bookings.workspace_id",
                "hotel_bookings.property_id",
                "hotel_bookings.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_booking_item_booking_scope",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id"],
            [
                "hotel_room_types.workspace_id",
                "hotel_room_types.property_id",
                "hotel_room_types.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_booking_item_room_scope",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "property_id", "room_type_id", "rate_plan_id"],
            [
                "hotel_rate_plans.workspace_id",
                "hotel_rate_plans.property_id",
                "hotel_rate_plans.room_type_id",
                "hotel_rate_plans.id",
            ],
            ondelete="RESTRICT",
            name="fk_hotel_booking_item_rate_scope",
        ),
        sa.UniqueConstraint("booking_id", name="uq_hotel_booking_single_item"),
        sa.CheckConstraint("quantity > 0", name="ck_hotel_booking_item_quantity"),
        sa.CheckConstraint("subtotal >= 0", name="ck_hotel_booking_item_subtotal"),
    )
    op.create_index(
        "ix_hotel_booking_items_booking_id", "hotel_booking_items", ["booking_id"]
    )

    op.create_table(
        "hotel_booking_events",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("booking_id"),
        sa.Column("event_type", booking_event_type, nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        _uuid("actor_user_id", nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "booking_id"],
            ["hotel_bookings.workspace_id", "hotel_bookings.id"],
            ondelete="RESTRICT",
            name="fk_hotel_booking_event_scope",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_hotel_booking_events_booking_created",
        "hotel_booking_events",
        ["booking_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("hotel_booking_events")
    op.drop_table("hotel_booking_items")
    op.drop_table("hotel_bookings")
    booking_event_type.drop(op.get_bind(), checkfirst=True)
    booking_status.drop(op.get_bind(), checkfirst=True)
    op.drop_constraint("uq_hotel_rate_plan_scope", "hotel_rate_plans", type_="unique")
    op.drop_constraint("uq_conversation_workspace_id", "conversations", type_="unique")
    op.drop_constraint("uq_customer_workspace_id", "customers", type_="unique")
