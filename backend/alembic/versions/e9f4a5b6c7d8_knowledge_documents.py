"""knowledge documents

Revision ID: e9f4a5b6c7d8
Revises: d8e3f4a5b6c7
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9f4a5b6c7d8"
down_revision: str | None = "d8e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    source_type = sa.Enum("UPLOAD", "TEXT", "URL", "FAQ", name="knowledge_source_type")
    document_status = sa.Enum(
        "UPLOADING",
        "PROCESSING",
        "READY",
        "FAILED",
        "DELETED",
        name="knowledge_document_status",
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("status", document_status, nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_knowledge_documents_workspace_id",
        "knowledge_documents",
        ["workspace_id"],
    )
    op.create_index(
        "ix_knowledge_documents_created_by",
        "knowledge_documents",
        ["created_by"],
    )
    op.create_index(
        "ix_knowledge_documents_status", "knowledge_documents", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_status", table_name="knowledge_documents")
    op.drop_index(
        "ix_knowledge_documents_created_by", table_name="knowledge_documents"
    )
    op.drop_index(
        "ix_knowledge_documents_workspace_id", table_name="knowledge_documents"
    )
    op.drop_table("knowledge_documents")
    sa.Enum(name="knowledge_document_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="knowledge_source_type").drop(op.get_bind(), checkfirst=True)
