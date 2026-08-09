"""Reusable ORM mixins enforcing platform-wide table conventions.

Every table in OneInFlow must have:
  - a UUID primary key (`id`)
  - `created_at` / `updated_at` timezone-aware timestamps

These mixins provide that foundation so models added in later sprints
inherit the conventions automatically. No domain models are defined here.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDMixin:
    """Adds a UUID v4 primary key named `id`."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class TimestampMixin:
    """Adds `created_at` / `updated_at` (UTC, timezone-aware)."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
