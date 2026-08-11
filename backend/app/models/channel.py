"""Workspace channel connections and truthful outbound delivery state."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.channels import ChannelType
from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class ChannelConnectionStatus(enum.StrEnum):
    DISCONNECTED = "DISCONNECTED"
    PENDING = "PENDING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class ChannelDeliveryStatus(enum.StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class ChannelConnection(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "channel_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider",
            "external_account_id",
            name="uq_channel_connection_workspace_account",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[ChannelType] = mapped_column(
        SAEnum(
            ChannelType,
            name="channel_type",
            values_callable=lambda cls: [item.value for item in cls],
            create_type=False,
        )
    )
    display_name: Mapped[str] = mapped_column(String(160))
    external_account_id: Mapped[str] = mapped_column(String(255))
    external_account_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ChannelConnectionStatus] = mapped_column(
        SAEnum(
            ChannelConnectionStatus,
            name="channel_connection_status",
            values_callable=lambda cls: [item.value for item in cls],
        ),
        default=ChannelConnectionStatus.PENDING,
    )
    credential_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    credential_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    credential_key_version: Mapped[str] = mapped_column(String(32), default="v1")
    connected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class ChannelMessageDelivery(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "channel_message_deliveries"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_channel_delivery_message"),
        Index(
            "ix_channel_delivery_connection_status",
            "channel_connection_id",
            "status",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    channel_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channel_connections.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[ChannelDeliveryStatus] = mapped_column(
        SAEnum(
            ChannelDeliveryStatus,
            name="channel_delivery_status",
            values_callable=lambda cls: [item.value for item in cls],
        ),
        default=ChannelDeliveryStatus.PENDING,
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
