"""Bounded operational state for supervised, idempotent scheduled jobs."""

from datetime import datetime

from sqlalchemy import TIMESTAMP, CheckConstraint, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ScheduledJobState(Base):
    """One row per job name; updated in place so storage stays bounded.

    The domain tables (and their append-only audit events) remain the
    authoritative history of what changed. This row only answers "is the job
    running, when did it last succeed, and is it failing?".
    """

    __tablename__ = "scheduled_job_states"
    __table_args__ = (
        CheckConstraint("consecutive_failures >= 0", name="ck_scheduled_job_failures"),
    )

    job_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_succeeded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_failed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_worker_id: Mapped[str | None] = mapped_column(String(128))
    last_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_runs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
