"""Workspace-scoped Guest CRM facts and immutable mutation events."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class CustomerPreferenceKey(enum.StrEnum):
    PREFERRED_ROOM_TYPE = "preferred_room_type"
    BED_PREFERENCE = "bed_preference"
    SMOKING_PREFERENCE = "smoking_preference"
    ACCESSIBILITY_REQUEST = "accessibility_request"
    ARRIVAL_PREFERENCE = "arrival_preference"
    LANGUAGE = "language"
    OTHER = "other"


class CustomerPreferenceSource(enum.StrEnum):
    CUSTOMER_PROVIDED = "CUSTOMER_PROVIDED"
    STAFF_CONFIRMED = "STAFF_CONFIRMED"
    IMPORT = "IMPORT"


class CustomerCRMEventType(enum.StrEnum):
    NOTE_ADDED = "NOTE_ADDED"
    TAG_ADDED = "TAG_ADDED"
    TAG_REMOVED = "TAG_REMOVED"
    PREFERENCE_ADDED = "PREFERENCE_ADDED"
    PREFERENCE_UPDATED = "PREFERENCE_UPDATED"


def _enum(cls, name):
    return SAEnum(
        cls, name=name, values_callable=lambda values: [item.value for item in values]
    )


class CustomerTag(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customer_tags"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_customer_tag_scope"),
        UniqueConstraint(
            "workspace_id", "normalized_name", name="uq_customer_tag_normalized"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(64), nullable=False)


class CustomerTagAssignment(UUIDMixin, Base):
    __tablename__ = "customer_tag_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="CASCADE",
            name="fk_customer_tag_assignment_customer_scope",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "tag_id"],
            ["customer_tags.workspace_id", "customer_tags.id"],
            ondelete="CASCADE",
            name="fk_customer_tag_assignment_tag_scope",
        ),
        UniqueConstraint(
            "workspace_id",
            "customer_id",
            "tag_id",
            name="uq_customer_tag_assignment",
        ),
        Index("ix_customer_tag_assignments_customer", "workspace_id", "customer_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class CustomerPreference(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customer_preferences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="CASCADE",
            name="fk_customer_preference_customer_scope",
        ),
        UniqueConstraint(
            "workspace_id", "customer_id", "key", name="uq_customer_preference_key"
        ),
        Index("ix_customer_preferences_customer", "workspace_id", "customer_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    key: Mapped[CustomerPreferenceKey] = mapped_column(
        _enum(CustomerPreferenceKey, "customer_preference_key")
    )
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[CustomerPreferenceSource] = mapped_column(
        _enum(CustomerPreferenceSource, "customer_preference_source")
    )
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class CustomerNote(UUIDMixin, Base):
    __tablename__ = "customer_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="CASCADE",
            name="fk_customer_note_customer_scope",
        ),
        Index("ix_customer_notes_customer_created", "customer_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class CustomerCRMEvent(UUIDMixin, Base):
    __tablename__ = "customer_crm_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "customer_id"],
            ["customers.workspace_id", "customers.id"],
            ondelete="CASCADE",
            name="fk_customer_crm_event_customer_scope",
        ),
        Index("ix_customer_crm_events_customer_created", "customer_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[CustomerCRMEventType] = mapped_column(
        _enum(CustomerCRMEventType, "customer_crm_event_type")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
