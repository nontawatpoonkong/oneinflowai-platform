"""Supervised, idempotent processing of scheduled campaign lifecycle changes.

The scheduler is a reliability mechanism only. ``PromotionService`` keeps
enforcing campaign and rule validity windows at validation and redemption time,
so a delayed or stopped scheduler can never extend a discount past its window.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.audit import AuditActorType, AuditArea
from app.models.promotion import PromotionCampaign, PromotionCampaignStatus
from app.models.scheduled_job import ScheduledJobState
from app.services.audit import AuditService
from app.services.promotion import CAMPAIGN_ACTIONS, CAMPAIGN_TRANSITIONS

logger = logging.getLogger(__name__)

JOB_NAME = "promotion_campaign_lifecycle"
_EXPIRABLE = (PromotionCampaignStatus.ACTIVE, PromotionCampaignStatus.PAUSED)


def safe_error_code(exc: BaseException) -> str:
    """Return a bounded code that never contains messages, SQL, or payloads."""

    if isinstance(exc, AppError):
        return exc.code[:64]
    return type(exc).__name__[:64]


class PromotionLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process_due(
        self,
        *,
        now: datetime | None = None,
        batch_size: int = 100,
        worker_id: str | None = None,
    ) -> dict:
        """Expire and mark-started one bounded batch inside a single transaction.

        Rows are claimed with ``FOR UPDATE SKIP LOCKED`` and re-filtered by
        status, so concurrent workers never transition (or audit) a campaign
        twice, and a repeated run after success is a no-op.
        """

        now = now or datetime.now(UTC)
        try:
            expired = await self._expire_due(now, batch_size)
            started = await self._start_due(now, batch_size)
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            await self._record(now, worker_id, processed=0, error=exc)
            raise
        processed = len(expired) + len(started)
        await self._record(now, worker_id, processed=processed, error=None)
        return {
            "expired": len(expired),
            "started": len(started),
            "processed": processed,
            "batch_full": len(expired) >= batch_size or len(started) >= batch_size,
        }

    async def _expire_due(self, now: datetime, limit: int) -> list[PromotionCampaign]:
        rows = list(
            (
                await self.session.execute(
                    select(PromotionCampaign)
                    .where(
                        PromotionCampaign.status.in_(_EXPIRABLE),
                        PromotionCampaign.valid_until.is_not(None),
                        PromotionCampaign.valid_until <= now,
                    )
                    .order_by(PromotionCampaign.valid_until, PromotionCampaign.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )
        audit = AuditService(self.session)
        for campaign in rows:
            target = PromotionCampaignStatus.EXPIRED
            if target not in CAMPAIGN_TRANSITIONS[campaign.status]:
                continue
            previous = campaign.status
            campaign.status = target
            audit.record(
                workspace_id=campaign.workspace_id,
                actor_user_id=None,
                actor_type=AuditActorType.AUTOMATION,
                action=CAMPAIGN_ACTIONS[target],
                area=AuditArea.PROMOTIONS,
                resource_type="PromotionCampaign",
                resource_id=campaign.id,
                metadata={
                    "trigger": "SCHEDULED",
                    "previous_status": previous.value,
                    "new_status": target.value,
                    "valid_until": campaign.valid_until.isoformat(),
                },
            )
        return rows

    async def _start_due(self, now: datetime, limit: int) -> list[PromotionCampaign]:
        rows = list(
            (
                await self.session.execute(
                    select(PromotionCampaign)
                    .where(
                        PromotionCampaign.status == PromotionCampaignStatus.ACTIVE,
                        PromotionCampaign.started_at.is_(None),
                        PromotionCampaign.valid_from.is_not(None),
                        PromotionCampaign.valid_from <= now,
                        or_(
                            PromotionCampaign.valid_until.is_(None),
                            PromotionCampaign.valid_until > now,
                        ),
                    )
                    .order_by(PromotionCampaign.valid_from, PromotionCampaign.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )
        audit = AuditService(self.session)
        for campaign in rows:
            campaign.started_at = now
            audit.record(
                workspace_id=campaign.workspace_id,
                actor_user_id=None,
                actor_type=AuditActorType.AUTOMATION,
                action="PROMOTION_CAMPAIGN_STARTED",
                area=AuditArea.PROMOTIONS,
                resource_type="PromotionCampaign",
                resource_id=campaign.id,
                metadata={
                    "trigger": "SCHEDULED",
                    "valid_from": campaign.valid_from.isoformat(),
                },
            )
        return rows

    async def _record(
        self,
        now: datetime,
        worker_id: str | None,
        *,
        processed: int,
        error: BaseException | None,
    ) -> None:
        table = ScheduledJobState.__table__
        values: dict = {
            "job_name": JOB_NAME,
            "last_started_at": now,
            "last_worker_id": worker_id[:128] if worker_id else None,
            "total_runs": 1,
            "updated_at": func.now(),
        }
        update: dict = {
            "last_started_at": now,
            "last_worker_id": values["last_worker_id"],
            "total_runs": table.c.total_runs + 1,
            "updated_at": func.now(),
        }
        if error is None:
            values |= {
                "last_succeeded_at": now,
                "consecutive_failures": 0,
                "last_processed": processed,
                "total_processed": processed,
            }
            update |= {
                "last_succeeded_at": now,
                "consecutive_failures": 0,
                "last_processed": processed,
                "total_processed": table.c.total_processed + processed,
            }
        else:
            code = safe_error_code(error)
            values |= {
                "last_failed_at": now,
                "last_error_code": code,
                "consecutive_failures": 1,
                "total_failures": 1,
            }
            update |= {
                "last_failed_at": now,
                "last_error_code": code,
                "consecutive_failures": table.c.consecutive_failures + 1,
                "total_failures": table.c.total_failures + 1,
            }
        try:
            await self.session.execute(
                insert(table)
                .values(**values)
                .on_conflict_do_update(index_elements=["job_name"], set_=update)
            )
            await self.session.commit()
        except Exception as exc:  # observability must never mask the job result
            await self.session.rollback()
            logger.error(
                "promotion.lifecycle.state_record_failed",
                extra={"error_type": type(exc).__name__},
            )

    async def status(self, *, stale_after_seconds: int, now: datetime | None = None):
        """Health signal derived from persisted job state and overdue work."""

        now = now or datetime.now(UTC)
        state = await self.session.get(ScheduledJobState, JOB_NAME)
        grace = now - timedelta(seconds=stale_after_seconds)
        overdue_expiry = int(
            await self.session.scalar(
                select(func.count())
                .select_from(PromotionCampaign)
                .where(
                    PromotionCampaign.status.in_(_EXPIRABLE),
                    PromotionCampaign.valid_until.is_not(None),
                    PromotionCampaign.valid_until <= grace,
                )
            )
            or 0
        )
        overdue_start = int(
            await self.session.scalar(
                select(func.count())
                .select_from(PromotionCampaign)
                .where(
                    PromotionCampaign.status == PromotionCampaignStatus.ACTIVE,
                    PromotionCampaign.started_at.is_(None),
                    PromotionCampaign.valid_from.is_not(None),
                    PromotionCampaign.valid_from <= grace,
                    or_(
                        PromotionCampaign.valid_until.is_(None),
                        PromotionCampaign.valid_until > now,
                    ),
                )
            )
            or 0
        )
        alerts = []
        if state is None or state.last_succeeded_at is None:
            health = "NOT_RUNNING"
            alerts.append("LIFECYCLE_NEVER_SUCCEEDED")
        elif state.last_succeeded_at < grace:
            health = "STALE"
            alerts.append("LIFECYCLE_STALE")
        elif state.consecutive_failures:
            health = "DEGRADED"
        else:
            health = "HEALTHY"
        if state is not None and state.consecutive_failures:
            alerts.append("LIFECYCLE_FAILING")
        if overdue_expiry or overdue_start:
            alerts.append("LIFECYCLE_BACKLOG")
        return {
            "job_name": JOB_NAME,
            "health": health,
            "alerts": alerts,
            "last_started_at": state.last_started_at if state else None,
            "last_succeeded_at": state.last_succeeded_at if state else None,
            "last_failed_at": state.last_failed_at if state else None,
            "last_error_code": state.last_error_code if state else None,
            "consecutive_failures": state.consecutive_failures if state else 0,
            "last_processed": state.last_processed if state else 0,
            "total_processed": state.total_processed if state else 0,
            "total_runs": state.total_runs if state else 0,
            "total_failures": state.total_failures if state else 0,
            "overdue_expiry": overdue_expiry,
            "overdue_start": overdue_start,
            "stale_after_seconds": stale_after_seconds,
            "generated_at": now,
        }
