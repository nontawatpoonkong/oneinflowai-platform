"""Workspace access requests, join settings, member grants, and audit events."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class WorkspaceAccessRequestStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class WorkspaceAccessAuditAction(enum.StrEnum):
    ACCESS_REQUESTED = "WORKSPACE_ACCESS_REQUESTED"
    ACCESS_APPROVED = "WORKSPACE_ACCESS_APPROVED"
    ACCESS_REJECTED = "WORKSPACE_ACCESS_REJECTED"
    ACCESS_CANCELLED = "WORKSPACE_ACCESS_CANCELLED"
    MEMBER_CAPABILITIES_CHANGED = "MEMBER_CAPABILITIES_CHANGED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    JOIN_CODE_REGENERATED = "JOIN_CODE_REGENERATED"
    JOIN_REQUESTS_TOGGLED = "JOIN_REQUESTS_TOGGLED"
    MEMBER_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"


class WorkspaceJoinSetting(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspace_join_settings"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    join_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    join_code_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    code_hint: Mapped[str | None] = mapped_column(String(4), nullable=True)


class WorkspaceAccessRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspace_access_requests"
    __table_args__ = (
        Index(
            "uq_workspace_access_request_pending",
            "workspace_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[WorkspaceAccessRequestStatus] = mapped_column(
        SAEnum(
            WorkspaceAccessRequestStatus,
            name="workspace_access_request_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=WorkspaceAccessRequestStatus.PENDING,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkspaceMemberCapability(UUIDMixin, Base):
    __tablename__ = "workspace_member_capabilities"
    __table_args__ = (
        UniqueConstraint(
            "membership_id",
            "capability",
            name="uq_workspace_member_capability",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )


class WorkspaceAccessAuditEvent(UUIDMixin, Base):
    __tablename__ = "workspace_access_audit_events"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    access_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_access_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    membership_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
