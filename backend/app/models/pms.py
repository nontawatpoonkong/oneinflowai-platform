"""Workspace-scoped PMS connections, mappings, sync history, and reconciliation."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class PMSSyncMode(enum.StrEnum):
    READ_ONLY_IMPORT = "READ_ONLY_IMPORT"


class PMSInventoryAuthority(enum.StrEnum):
    LOCAL = "LOCAL"
    PMS = "PMS"


class PMSConnectionStatus(enum.StrEnum):
    PENDING = "PENDING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"
    DISCONNECTED = "DISCONNECTED"


class PMSEntityType(enum.StrEnum):
    PROPERTY = "PROPERTY"
    ROOM_TYPE = "ROOM_TYPE"
    ROOM = "ROOM"
    RATE_PLAN = "RATE_PLAN"
    RESERVATION = "RESERVATION"


class PMSSyncRunStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class PMSIssueStatus(enum.StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class PMSConnection(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pms_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_pms_connection_scope"),
        CheckConstraint(
            "sync_mode = 'READ_ONLY_IMPORT'", name="ck_pms_connection_read_only"
        ),
        CheckConstraint(
            "inventory_authority IN ('LOCAL', 'PMS')",
            name="ck_pms_connection_inventory_authority",
        ),
        Index("ix_pms_connections_workspace_active", "workspace_id", "active"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    status: Mapped[str] = mapped_column(
        String(16), default=PMSConnectionStatus.PENDING.value
    )
    sync_mode: Mapped[str] = mapped_column(
        String(32), default=PMSSyncMode.READ_ONLY_IMPORT.value
    )
    inventory_authority: Mapped[str] = mapped_column(
        String(16), default=PMSInventoryAuthority.LOCAL.value
    )
    credential_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    credential_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    credential_key_version: Mapped[str] = mapped_column(String(32))
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    sync_cursor: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    last_failed_sync_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class PMSExternalMapping(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pms_external_mappings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["pms_connections.workspace_id", "pms_connections.id"],
            ondelete="CASCADE",
            name="fk_pms_mapping_connection_scope",
        ),
        UniqueConstraint(
            "connection_id",
            "entity_type",
            "external_id",
            name="uq_pms_mapping_external_identity",
        ),
        Index(
            "ix_pms_mappings_local",
            "workspace_id",
            "entity_type",
            "local_entity_id",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    entity_type: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(255))
    local_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    external_version: Mapped[str | None] = mapped_column(String(255))
    external_updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )


class PMSSyncRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pms_sync_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["pms_connections.workspace_id", "pms_connections.id"],
            ondelete="CASCADE",
            name="fk_pms_sync_run_connection_scope",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_pms_sync_run_scope"),
        Index(
            "uq_pms_sync_run_active_connection",
            "connection_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
        Index(
            "ix_pms_sync_runs_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(16), default=PMSSyncRunStatus.PENDING.value
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cursor_before: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    cursor_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    entities_fetched: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    entities_applied: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    conflict_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    warning_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    initiated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class PMSReconciliationIssue(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pms_reconciliation_issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["pms_connections.workspace_id", "pms_connections.id"],
            ondelete="CASCADE",
            name="fk_pms_issue_connection_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "sync_run_id"],
            ["pms_sync_runs.workspace_id", "pms_sync_runs.id"],
            ondelete="CASCADE",
            name="fk_pms_issue_run_scope",
        ),
        Index(
            "uq_pms_issue_open_identity",
            "connection_id",
            "entity_type",
            "external_id",
            "issue_type",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
        ),
        Index(
            "ix_pms_issues_workspace_status",
            "workspace_id",
            "status",
            "created_at",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sync_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    entity_type: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(255))
    local_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    issue_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(16), default=PMSIssueStatus.OPEN.value, server_default="OPEN"
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
