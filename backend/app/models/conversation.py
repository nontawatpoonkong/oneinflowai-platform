"""Conversation model — the channel-agnostic communication hub."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.channels import ChannelType
from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.message import Message
    from app.models.user import User
    from app.models.workspace import Workspace


class ConversationStatus(enum.StrEnum):
    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ConversationMode(enum.StrEnum):
    AUTO = "AUTO"
    COPILOT = "COPILOT"
    HUMAN = "HUMAN"


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(
            ConversationStatus,
            name="conversation_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=ConversationStatus.OPEN,
    )
    channel: Mapped[ChannelType] = mapped_column(
        SAEnum(
            ChannelType,
            name="channel_type",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_user: Mapped["User | None"] = relationship(foreign_keys=[assigned_user_id])
    external_conversation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, index=True
    )

    # AI takeover control (foundation only; no AI behavior yet).
    ai_mode: Mapped[ConversationMode] = mapped_column(
        SAEnum(
            ConversationMode,
            name="conversation_mode",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=ConversationMode.AUTO,
        server_default=ConversationMode.AUTO.value,
    )
    taken_over_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    taken_over_user: Mapped["User | None"] = relationship(foreign_keys=[taken_over_by])
    taken_over_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # One-directional navigation (existing models are not modified).
    workspace: Mapped["Workspace"] = relationship()
    customer: Mapped["Customer"] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
