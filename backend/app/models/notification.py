"""Recipient-scoped in-app operational notifications."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class NotificationType(enum.StrEnum):
    CONVERSATION_HANDOFF = "CONVERSATION_HANDOFF"
    CONVERSATION_ASSIGNED = "CONVERSATION_ASSIGNED"
    NEW_CUSTOMER_MESSAGE = "NEW_CUSTOMER_MESSAGE"
    ACTION_CREATED = "ACTION_CREATED"
    ACTION_ASSIGNED = "ACTION_ASSIGNED"
    PAYMENT_VERIFIED = "PAYMENT_VERIFIED"
    PAYMENT_REVIEW_REQUIRED = "PAYMENT_REVIEW_REQUIRED"


class NotificationEntityType(enum.StrEnum):
    CONVERSATION = "CONVERSATION"
    ACTION = "ACTION"
    PAYMENT = "PAYMENT"


class Notification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "recipient_user_id",
            "deduplication_key",
            name="uq_notification_recipient_deduplication",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(
            NotificationType,
            name="notification_type",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(320))
    entity_type: Mapped[NotificationEntityType] = mapped_column(
        SAEnum(
            NotificationEntityType,
            name="notification_entity_type",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    read_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    deduplication_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
