"""Persisted, workspace-scoped action field collection state."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin
from app.models.action import ActionActorType


class ActionCollectionStatus(enum.StrEnum):
    COLLECTING = "COLLECTING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class ActionCollectionSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "action_collection_sessions"
    __table_args__ = (
        UniqueConstraint(
            "action_idempotency_key", name="uq_action_collection_idempotency_key"
        ),
        Index("ix_action_collection_workspace_status", "workspace_id", "status"),
        Index("ix_action_collection_conversation", "conversation_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    action_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("action_definitions.id", ondelete="RESTRICT"),
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    action_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("action_requests.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[ActionCollectionStatus] = mapped_column(
        SAEnum(
            ActionCollectionStatus,
            name="action_collection_status",
            values_callable=lambda cls: [item.value for item in cls],
        ),
        default=ActionCollectionStatus.COLLECTING,
    )
    collected_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    missing_fields: Mapped[list[str]] = mapped_column(JSONB, default=list)
    invalid_fields: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(64))
    confirmation_expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    action_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_type: Mapped[ActionActorType] = mapped_column(
        SAEnum(
            ActionActorType,
            name="action_collection_actor_type",
            values_callable=lambda cls: [item.value for item in cls],
        ),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
