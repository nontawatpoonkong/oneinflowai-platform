"""Track booking payment application separately from verification.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

application_status = postgresql.ENUM(
    "UNAPPLIED", "APPLIED", "REQUIRES_REVIEW", name="payment_application_status"
)
application_reason = postgresql.ENUM(
    "BOOKING_EXPIRED",
    "BOOKING_CANCELLED",
    "BOOKING_ALREADY_CONFIRMED",
    "AMOUNT_MISMATCH",
    "CURRENCY_MISMATCH",
    "PAYMENT_ALREADY_APPLIED",
    "BOOKING_LINK_CONFLICT",
    "INVALID_BOOKING_STATE",
    "PAYMENT_NOT_VERIFIED",
    name="payment_application_reason",
)


def upgrade() -> None:
    bind = op.get_bind()
    application_status.create(bind, checkfirst=True)
    application_reason.create(bind, checkfirst=True)
    op.add_column(
        "payments",
        sa.Column(
            "booking_application_status",
            postgresql.ENUM(name="payment_application_status", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "booking_application_reason",
            postgresql.ENUM(name="payment_application_reason", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("payments", sa.Column("booking_review_note", sa.String(1000)))
    op.add_column(
        "payments", sa.Column("booking_reviewed_at", sa.TIMESTAMP(timezone=True))
    )
    op.add_column(
        "payments",
        sa.Column("booking_reviewed_by_user_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_payment_booking_reviewer",
        "payments",
        "users",
        ["booking_reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        "UPDATE payments SET booking_application_status = CASE "
        "WHEN booking_applied_at IS NOT NULL "
        "THEN 'APPLIED'::payment_application_status "
        "ELSE 'UNAPPLIED'::payment_application_status END "
        "WHERE booking_id IS NOT NULL"
    )
    op.drop_constraint("uq_payment_booking", "payments", type_="unique")
    op.create_index(
        "uq_payment_booking_applied",
        "payments",
        ["workspace_id", "booking_id"],
        unique=True,
        postgresql_where=sa.text("booking_applied_at IS NOT NULL"),
    )
    op.create_index(
        "ix_payments_application_review",
        "payments",
        ["workspace_id", "booking_application_status"],
    )
    op.create_check_constraint(
        "ck_payment_applied_has_booking",
        "payments",
        "booking_applied_at IS NULL OR booking_id IS NOT NULL",
    )
    for event in (
        "PAYMENT_REQUIRES_REVIEW",
        "REPLACEMENT_PAYMENT_LINKED",
        "PAYMENT_REVIEW_ACKNOWLEDGED",
    ):
        op.execute(
            f"ALTER TYPE hotel_booking_event_type ADD VALUE IF NOT EXISTS '{event}'"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM hotel_booking_events WHERE event_type::text "
            "IN ('PAYMENT_REQUIRES_REVIEW', 'REPLACEMENT_PAYMENT_LINKED', "
            "'PAYMENT_REVIEW_ACKNOWLEDGED'))"
        )
    ).scalar():
        raise RuntimeError("Cannot downgrade while reconciliation audit events exist")
    if bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM payments WHERE booking_id IS NOT NULL "
            "GROUP BY workspace_id, booking_id HAVING count(*) > 1)"
        )
    ).scalar():
        raise RuntimeError("Cannot downgrade while replacement payment attempts exist")
    op.drop_constraint("ck_payment_applied_has_booking", "payments", type_="check")
    op.drop_index("ix_payments_application_review", table_name="payments")
    op.drop_index("uq_payment_booking_applied", table_name="payments")
    op.create_unique_constraint(
        "uq_payment_booking", "payments", ["workspace_id", "booking_id"]
    )
    op.drop_constraint("fk_payment_booking_reviewer", "payments", type_="foreignkey")
    op.drop_column("payments", "booking_reviewed_by_user_id")
    op.drop_column("payments", "booking_reviewed_at")
    op.drop_column("payments", "booking_review_note")
    op.drop_column("payments", "booking_application_reason")
    op.drop_column("payments", "booking_application_status")
    application_reason.drop(bind, checkfirst=True)
    application_status.drop(bind, checkfirst=True)
    op.execute(
        "ALTER TYPE hotel_booking_event_type RENAME TO hotel_booking_event_type_old"
    )
    old_type = postgresql.ENUM(
        "BOOKING_CREATED",
        "HOLD_CREATED",
        "HOLD_EXPIRED",
        "BOOKING_CANCELLED",
        "PENDING_PAYMENT_STARTED",
        "PAYMENT_LINKED",
        "BOOKING_CONFIRMED",
        name="hotel_booking_event_type",
    )
    old_type.create(bind, checkfirst=False)
    op.execute(
        "ALTER TABLE hotel_booking_events ALTER COLUMN event_type "
        "TYPE hotel_booking_event_type USING event_type::text::hotel_booking_event_type"
    )
    op.execute("DROP TYPE hotel_booking_event_type_old")
