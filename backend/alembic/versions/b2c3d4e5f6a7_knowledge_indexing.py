"""knowledge indexing metadata

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    index_status = sa.Enum(
        "PENDING", "INDEXING", "INDEXED", "FAILED", name="knowledge_index_status"
    )
    index_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "index_status",
            index_status,
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("indexed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("index_error_code", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_knowledge_documents_index_status",
        "knowledge_documents",
        ["index_status"],
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_version", sa.String(length=192), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("indexed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "indexed_at")
    op.drop_column("knowledge_chunks", "embedding_version")
    op.drop_column("knowledge_chunks", "embedding_model")
    op.drop_index(
        "ix_knowledge_documents_index_status", table_name="knowledge_documents"
    )
    op.drop_column("knowledge_documents", "index_error_code")
    op.drop_column("knowledge_documents", "indexed_at")
    op.drop_column("knowledge_documents", "index_status")
    sa.Enum(name="knowledge_index_status").drop(op.get_bind(), checkfirst=True)
