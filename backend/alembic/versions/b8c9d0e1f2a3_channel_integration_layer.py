"""channel integration layer

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

connection_status = postgresql.ENUM(
    "DISCONNECTED",
    "PENDING",
    "CONNECTED",
    "ERROR",
    name="channel_connection_status",
    create_type=False,
)
delivery_status = postgresql.ENUM(
    "PENDING",
    "SENT",
    "FAILED",
    name="channel_delivery_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    orphan = bind.execute(
        sa.text("""
        SELECT ci.id FROM customer_identities ci
        LEFT JOIN customers c ON c.id = ci.customer_id
        WHERE c.id IS NULL LIMIT 1
    """)
    ).first()
    if orphan:
        raise RuntimeError("Cannot migrate orphaned customer identity")

    connection_status.create(bind, checkfirst=True)
    delivery_status.create(bind, checkfirst=True)
    op.create_table(
        "channel_connections",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            postgresql.ENUM(name="channel_type", create_type=False),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("external_account_id", sa.String(255), nullable=False),
        sa.Column("external_account_name", sa.String(255), nullable=True),
        sa.Column("status", connection_status, nullable=False),
        sa.Column("credential_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("credential_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("credential_key_version", sa.String(32), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "external_account_id",
            name="uq_channel_connection_workspace_account",
        ),
    )
    op.create_index(
        "ix_channel_connections_workspace_id", "channel_connections", ["workspace_id"]
    )

    op.add_column(
        "customer_identities", sa.Column("workspace_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "customer_identities",
        sa.Column("channel_connection_id", sa.Uuid(), nullable=True),
    )
    bind.execute(
        sa.text("""
        UPDATE customer_identities ci SET workspace_id = c.workspace_id
        FROM customers c WHERE c.id = ci.customer_id
    """)
    )
    op.alter_column("customer_identities", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_customer_identity_workspace",
        "customer_identities",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_customer_identity_connection",
        "customer_identities",
        "channel_connections",
        ["channel_connection_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_customer_identities_workspace_id", "customer_identities", ["workspace_id"]
    )
    op.create_index(
        "ix_customer_identities_channel_connection_id",
        "customer_identities",
        ["channel_connection_id"],
    )
    op.create_unique_constraint(
        "uq_customer_identity_connection_user",
        "customer_identities",
        ["channel_connection_id", "external_user_id"],
    )

    op.add_column(
        "conversations", sa.Column("channel_connection_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_conversation_channel_connection",
        "conversations",
        "channel_connections",
        ["channel_connection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversations_channel_connection_id",
        "conversations",
        ["channel_connection_id"],
    )

    op.create_table(
        "channel_message_deliveries",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("channel_connection_id", sa.Uuid(), nullable=False),
        sa.Column("status", delivery_status, nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["channel_connection_id"], ["channel_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_channel_delivery_message"),
    )
    op.create_index(
        "ix_channel_message_deliveries_workspace_id",
        "channel_message_deliveries",
        ["workspace_id"],
    )
    op.create_index(
        "ix_channel_message_deliveries_message_id",
        "channel_message_deliveries",
        ["message_id"],
    )
    op.create_index(
        "ix_channel_message_deliveries_channel_connection_id",
        "channel_message_deliveries",
        ["channel_connection_id"],
    )
    op.create_index(
        "ix_channel_delivery_connection_status",
        "channel_message_deliveries",
        ["channel_connection_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("channel_message_deliveries")
    op.drop_index("ix_conversations_channel_connection_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversation_channel_connection", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "channel_connection_id")
    op.drop_constraint(
        "uq_customer_identity_connection_user", "customer_identities", type_="unique"
    )
    op.drop_index(
        "ix_customer_identities_channel_connection_id", table_name="customer_identities"
    )
    op.drop_index(
        "ix_customer_identities_workspace_id", table_name="customer_identities"
    )
    op.drop_constraint(
        "fk_customer_identity_connection", "customer_identities", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_customer_identity_workspace", "customer_identities", type_="foreignkey"
    )
    op.drop_column("customer_identities", "channel_connection_id")
    op.drop_column("customer_identities", "workspace_id")
    op.drop_table("channel_connections")
    bind = op.get_bind()
    delivery_status.drop(bind, checkfirst=True)
    connection_status.drop(bind, checkfirst=True)
