"""Add workspace-scoped Guest CRM facts and audit events.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

preference_key = postgresql.ENUM(
    "preferred_room_type",
    "bed_preference",
    "smoking_preference",
    "accessibility_request",
    "arrival_preference",
    "language",
    "other",
    name="customer_preference_key",
)
preference_source = postgresql.ENUM(
    "CUSTOMER_PROVIDED",
    "STAFF_CONFIRMED",
    "IMPORT",
    name="customer_preference_source",
)
crm_event_type = postgresql.ENUM(
    "NOTE_ADDED",
    "TAG_ADDED",
    "TAG_REMOVED",
    "PREFERENCE_ADDED",
    "PREFERENCE_UPDATED",
    name="customer_crm_event_type",
)


def upgrade() -> None:
    bind = op.get_bind()
    preference_key.create(bind, checkfirst=True)
    preference_source.create(bind, checkfirst=True)
    crm_event_type.create(bind, checkfirst=True)
    op.create_table(
        "customer_tags",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("normalized_name", sa.String(64), nullable=False),
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
        sa.UniqueConstraint("workspace_id", "id", name="uq_customer_tag_scope"),
        sa.UniqueConstraint(
            "workspace_id", "normalized_name", name="uq_customer_tag_normalized"
        ),
    )
    op.create_index("ix_customer_tags_workspace_id", "customer_tags", ["workspace_id"])
    op.create_table(
        "customer_tag_assignments",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            name="fk_customer_tag_assignment_customer_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "tag_id"],
            ["customer_tags.workspace_id", "customer_tags.id"],
            name="fk_customer_tag_assignment_tag_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "customer_id", "tag_id", name="uq_customer_tag_assignment"
        ),
    )
    op.create_index(
        "ix_customer_tag_assignments_customer",
        "customer_tag_assignments",
        ["workspace_id", "customer_id"],
    )
    op.create_table(
        "customer_preferences",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "key",
            postgresql.ENUM(name="customer_preference_key", create_type=False),
            nullable=False,
        ),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM(name="customer_preference_source", create_type=False),
            nullable=False,
        ),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True)),
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
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            name="fk_customer_preference_customer_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "customer_id", "key", name="uq_customer_preference_key"
        ),
    )
    op.create_index(
        "ix_customer_preferences_customer",
        "customer_preferences",
        ["workspace_id", "customer_id"],
    )
    op.create_table(
        "customer_notes",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            name="fk_customer_note_customer_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_notes_workspace_id", "customer_notes", ["workspace_id"]
    )
    op.create_index(
        "ix_customer_notes_customer_created",
        "customer_notes",
        ["customer_id", "created_at"],
    )
    op.create_table(
        "customer_crm_events",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM(name="customer_crm_event_type", create_type=False),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            name="fk_customer_crm_event_customer_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_crm_events_workspace_id", "customer_crm_events", ["workspace_id"]
    )
    op.create_index(
        "ix_customer_crm_events_customer_created",
        "customer_crm_events",
        ["customer_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_crm_events_customer_created", table_name="customer_crm_events"
    )
    op.drop_index(
        "ix_customer_crm_events_workspace_id", table_name="customer_crm_events"
    )
    op.drop_table("customer_crm_events")
    op.drop_index("ix_customer_notes_customer_created", table_name="customer_notes")
    op.drop_index("ix_customer_notes_workspace_id", table_name="customer_notes")
    op.drop_table("customer_notes")
    op.drop_index("ix_customer_preferences_customer", table_name="customer_preferences")
    op.drop_table("customer_preferences")
    op.drop_index(
        "ix_customer_tag_assignments_customer", table_name="customer_tag_assignments"
    )
    op.drop_table("customer_tag_assignments")
    op.drop_index("ix_customer_tags_workspace_id", table_name="customer_tags")
    op.drop_table("customer_tags")
    crm_event_type.drop(op.get_bind(), checkfirst=True)
    preference_source.drop(op.get_bind(), checkfirst=True)
    preference_key.drop(op.get_bind(), checkfirst=True)
