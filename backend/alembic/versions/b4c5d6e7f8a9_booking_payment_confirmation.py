"""Link customer payments to bookings and record single-use confirmation.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("booking_applied_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_payment_booking_scope",
        "payments",
        "hotel_bookings",
        ["workspace_id", "booking_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_payment_booking", "payments", ["workspace_id", "booking_id"]
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
    op.execute(
        "ALTER TYPE hotel_booking_event_type ADD VALUE IF NOT EXISTS 'PAYMENT_LINKED'"
    )
    op.execute(
        "ALTER TYPE hotel_booking_event_type "
        "ADD VALUE IF NOT EXISTS 'BOOKING_CONFIRMED'"
    )


def downgrade() -> None:
    # PostgreSQL enum values are rebuilt so this downgrade fully restores the
    # prior type. Existing Sprint 10.2 events must be removed before downgrade.
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM hotel_booking_events "
            "WHERE event_type::text IN ('PAYMENT_LINKED', 'BOOKING_CONFIRMED'))"
        )
    ).scalar():
        raise RuntimeError("Cannot downgrade while payment confirmation events exist")
    op.drop_index("ix_payments_booking_id", table_name="payments")
    op.drop_constraint("uq_payment_booking", "payments", type_="unique")
    op.drop_constraint("fk_payment_booking_scope", "payments", type_="foreignkey")
    op.drop_column("payments", "booking_applied_at")
    op.drop_column("payments", "booking_id")
    op.execute(
        "ALTER TYPE hotel_booking_event_type "
        "RENAME TO hotel_booking_event_type_old"
    )
    old_type = postgresql.ENUM(
        "BOOKING_CREATED",
        "HOLD_CREATED",
        "HOLD_EXPIRED",
        "BOOKING_CANCELLED",
        "PENDING_PAYMENT_STARTED",
        name="hotel_booking_event_type",
    )
    old_type.create(connection, checkfirst=False)
    op.execute(
        "ALTER TABLE hotel_booking_events ALTER COLUMN event_type "
        "TYPE hotel_booking_event_type USING event_type::text::hotel_booking_event_type"
    )
    op.execute("DROP TYPE hotel_booking_event_type_old")
