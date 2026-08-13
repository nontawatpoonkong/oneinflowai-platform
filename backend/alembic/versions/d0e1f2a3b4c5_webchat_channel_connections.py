"""Grandfather historically used Workspace WebChat connections.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMESPACE = uuid.UUID("7f44af63-d6d6-4c99-bd8b-454306de36a1")


def _connection_id(workspace_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, str(workspace_id))


def upgrade() -> None:
    bind = op.get_bind()
    workspace_ids = bind.execute(
        sa.text(
            """
            SELECT DISTINCT c.workspace_id
            FROM webchat_sessions ws
            JOIN conversations c ON c.id = ws.conversation_id
            WHERE c.channel = 'web'
            """
        )
    ).scalars()
    now = datetime.now(UTC)
    for workspace_id in workspace_ids:
        existing = bind.execute(
            sa.text(
                """
                SELECT id FROM channel_connections
                WHERE workspace_id = :workspace_id AND provider = 'web'
                ORDER BY created_at, id LIMIT 1
                """
            ),
            {"workspace_id": workspace_id},
        ).scalar_one_or_none()
        connection_id = existing or _connection_id(workspace_id)
        if existing is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO channel_connections (
                        id, workspace_id, provider, display_name,
                        external_account_id, external_account_name, status,
                        credential_ciphertext, credential_nonce,
                        credential_key_version, connected_at, created_at, updated_at
                    ) VALUES (
                        :id, :workspace_id, 'web', 'WebChat',
                        :external_account_id, NULL, 'CONNECTED',
                        :empty_bytes, :empty_bytes, 'none', :now, :now, :now
                    )
                    """
                ),
                {
                    "id": connection_id,
                    "workspace_id": workspace_id,
                    "external_account_id": str(workspace_id),
                    "empty_bytes": b"",
                    "now": now,
                },
            )
        bind.execute(
            sa.text(
                """
                UPDATE conversations
                SET channel_connection_id = :connection_id
                WHERE workspace_id = :workspace_id
                  AND channel = 'web'
                  AND channel_connection_id IS NULL
                """
            ),
            {"connection_id": connection_id, "workspace_id": workspace_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    workspace_ids = bind.execute(
        sa.text(
            """
            SELECT DISTINCT c.workspace_id
            FROM webchat_sessions ws
            JOIN conversations c ON c.id = ws.conversation_id
            WHERE c.channel = 'web'
            """
        )
    ).scalars()
    for workspace_id in workspace_ids:
        connection_id = _connection_id(workspace_id)
        bind.execute(
            sa.text(
                """
                UPDATE conversations SET channel_connection_id = NULL
                WHERE channel_connection_id = :connection_id
                """
            ),
            {"connection_id": connection_id},
        )
        bind.execute(
            sa.text("DELETE FROM channel_connections WHERE id = :connection_id"),
            {"connection_id": connection_id},
        )
