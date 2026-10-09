"""Deterministic evaluator and bounded automation execution runner."""

import logging
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError
from app.models.automation import (
    AutomationDefinition,
    AutomationExecution,
    AutomationExecutionStatus,
    AutomationScheduleMode,
    AutomationWorkerHeartbeat,
    AutomationWorkerState,
    DomainEventOutbox,
    OutboxState,
)
from app.models.conversation import Conversation
from app.models.hotel import Property
from app.models.message import Message, MessageType, SenderType
from app.models.notification import NotificationEntityType, NotificationType
from app.schemas.automation import (
    AutomationCondition,
    AutomationDefinitionCreate,
    AutomationDefinitionPatch,
    AutomationDefinitionResponse,
    AutomationExecutionResponse,
    ConditionOperator,
    validate_template,
)
from app.services.channel_delivery import ChannelDeliveryService
from app.services.notification import NotificationService

MAX_ATTEMPTS = 3
RETRY_DELAYS = (60, 300, 900)
logger = logging.getLogger(__name__)


class AutomationValidationError(AppError):
    status_code = 422
    code = "AUTOMATION_INVALID"
    message = "Automation configuration is invalid"


class AutomationActionError(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class AutomationExecutionStateError(AppError):
    status_code = 409
    code = "AUTOMATION_EXECUTION_STATE_INVALID"
    message = "Automation execution state does not allow this operation"


class AutomationService:
    def __init__(self, session, *, channel_provider_factory=None) -> None:
        self.session = session
        self.channel_provider_factory = channel_provider_factory

    async def create(self, workspace_id, user_id, data: AutomationDefinitionCreate):
        item = AutomationDefinition(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            **data.model_dump(mode="json"),
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return AutomationDefinitionResponse.model_validate(item)

    @staticmethod
    def validate(data: AutomationDefinitionCreate) -> dict[str, bool]:
        # Pydantic has already validated the complete bounded contract.
        return {"valid": True}

    async def get(self, workspace_id, automation_id):
        item = await self.session.scalar(
            select(AutomationDefinition).where(
                AutomationDefinition.workspace_id == workspace_id,
                AutomationDefinition.id == automation_id,
            )
        )
        if item is None:
            raise NotFoundError("Automation not found")
        return item

    async def update(
        self,
        workspace_id,
        automation_id,
        data: AutomationDefinitionPatch,
    ):
        item = await self.get(workspace_id, automation_id)
        current = {
            "name": item.name,
            "active": item.active,
            "trigger_event_type": item.trigger_event_type,
            "trigger_version": item.trigger_version,
            "conditions": item.conditions,
            "action_type": item.action_type,
            "action_config": item.action_config,
            "schedule_mode": item.schedule_mode,
            "schedule_config": item.schedule_config,
        }
        current.update(data.model_dump(exclude_unset=True, mode="json"))
        validated = AutomationDefinitionCreate.model_validate(current)
        for key, value in validated.model_dump(mode="json").items():
            setattr(item, key, value)
        await self.session.commit()
        await self.session.refresh(item)
        return AutomationDefinitionResponse.model_validate(item)

    async def set_active(self, workspace_id, automation_id, active: bool):
        item = await self.get(workspace_id, automation_id)
        item.active = active
        await self.session.commit()
        await self.session.refresh(item)
        return AutomationDefinitionResponse.model_validate(item)

    async def list(self, workspace_id, *, page: int, page_size: int):
        total = int(
            await self.session.scalar(
                select(func.count(AutomationDefinition.id)).where(
                    AutomationDefinition.workspace_id == workspace_id
                )
            )
            or 0
        )
        items = list(
            await self.session.scalars(
                select(AutomationDefinition)
                .where(AutomationDefinition.workspace_id == workspace_id)
                .order_by(AutomationDefinition.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return {
            "items": [
                AutomationDefinitionResponse.model_validate(item).model_dump(
                    mode="json"
                )
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def list_executions(self, workspace_id, *, page: int, page_size: int):
        total = int(
            await self.session.scalar(
                select(func.count(AutomationExecution.id)).where(
                    AutomationExecution.workspace_id == workspace_id
                )
            )
            or 0
        )
        items = list(
            await self.session.scalars(
                select(AutomationExecution)
                .where(AutomationExecution.workspace_id == workspace_id)
                .order_by(AutomationExecution.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        counts = dict(
            (
                await self.session.execute(
                    select(AutomationExecution.status, func.count())
                    .where(AutomationExecution.workspace_id == workspace_id)
                    .group_by(AutomationExecution.status)
                )
            ).all()
        )
        return {
            "items": [
                AutomationExecutionResponse.model_validate(item).model_dump(mode="json")
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "counts": {
                status: int(counts.get(status, 0))
                for status in ("PENDING", "RUNNING", "SUCCEEDED", "FAILED")
            },
        }

    async def evaluate_events(self, *, batch_size: int = 50, now=None) -> int:
        now = now or datetime.now(UTC)
        events = list(
            await self.session.scalars(
                select(DomainEventOutbox)
                .where(
                    DomainEventOutbox.state == OutboxState.PENDING.value,
                    DomainEventOutbox.available_at <= now,
                )
                .order_by(DomainEventOutbox.created_at, DomainEventOutbox.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for event in events:
            event.state = OutboxState.PROCESSING.value
            event.attempt_count += 1
            definitions = list(
                await self.session.scalars(
                    select(AutomationDefinition).where(
                        AutomationDefinition.workspace_id == event.workspace_id,
                        AutomationDefinition.active.is_(True),
                        AutomationDefinition.trigger_event_type == event.event_type,
                        AutomationDefinition.trigger_version == event.event_version,
                    )
                )
            )
            for definition in definitions:
                if not self._matches(definition.conditions, event.payload):
                    continue
                scheduled_for = await self._scheduled_for(definition, event)
                await self.session.execute(
                    insert(AutomationExecution)
                    .values(
                        id=uuid.uuid4(),
                        workspace_id=event.workspace_id,
                        automation_id=definition.id,
                        event_id=event.id,
                        status=AutomationExecutionStatus.PENDING.value,
                        scheduled_for=scheduled_for,
                        attempt_count=0,
                        effect_key=f"automation:{definition.id}:{event.id}",
                    )
                    .on_conflict_do_nothing(
                        index_elements=["automation_id", "event_id"]
                    )
                )
            event.state = OutboxState.PROCESSED.value
            event.processed_at = now
        await self.session.commit()
        return len(events)

    async def recover_stale_executions(
        self,
        *,
        stale_seconds: int,
        batch_size: int,
        now=None,
        worker_id: str | None = None,
    ) -> int:
        now = now or datetime.now(UTC)
        stale_before = now - timedelta(seconds=stale_seconds)
        executions = list(
            await self.session.scalars(
                select(AutomationExecution)
                .where(
                    AutomationExecution.status
                    == AutomationExecutionStatus.RUNNING.value,
                    AutomationExecution.started_at <= stale_before,
                )
                .order_by(AutomationExecution.started_at, AutomationExecution.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for execution in executions:
            self._record_failure(
                execution,
                "WORKER_INTERRUPTED",
                now,
                source="stale_recovery",
            )
            execution.last_error_code = "WORKER_INTERRUPTED"
            execution.last_recovered_at = now
            execution.claimed_by_worker_id = None
            if execution.attempt_count < MAX_ATTEMPTS:
                execution.status = AutomationExecutionStatus.PENDING.value
                execution.scheduled_for = now + timedelta(
                    seconds=RETRY_DELAYS[max(execution.attempt_count - 1, 0)]
                )
                execution.terminal_failure = False
            else:
                execution.status = AutomationExecutionStatus.FAILED.value
                execution.completed_at = now
                execution.terminal_failure = True
            logger.warning(
                "automation.execution.stale_recovered",
                extra=self._log_context(execution, worker_id=worker_id),
            )
        await self.session.commit()
        return len(executions)

    async def run_executions(
        self,
        *,
        batch_size: int = 20,
        now=None,
        worker_id: str = "automation-worker",
        stop_event=None,
    ) -> int:
        now = now or datetime.now(UTC)
        executions = list(
            await self.session.scalars(
                select(AutomationExecution)
                .where(
                    AutomationExecution.status
                    == AutomationExecutionStatus.PENDING.value,
                    AutomationExecution.scheduled_for <= now,
                )
                .order_by(AutomationExecution.scheduled_for, AutomationExecution.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for execution in executions:
            execution.status = AutomationExecutionStatus.RUNNING.value
            execution.started_at = now
            execution.claimed_by_worker_id = worker_id
            logger.info(
                "automation.execution.claimed",
                extra=self._log_context(execution, worker_id=worker_id),
            )
        await self.session.commit()

        processed = 0
        for index, execution in enumerate(executions):
            if stop_event is not None and stop_event.is_set():
                await self._release_claims(
                    executions[index:], now=now, worker_id=worker_id
                )
                break
            execution.attempt_count += 1
            logger.info(
                "automation.execution.started",
                extra=self._log_context(execution, worker_id=worker_id),
            )
            try:
                await self._execute(execution)
                execution.status = AutomationExecutionStatus.SUCCEEDED.value
                execution.completed_at = datetime.now(UTC)
                execution.last_error_code = None
                execution.terminal_failure = False
                logger.info(
                    "automation.execution.succeeded",
                    extra=self._log_context(execution, worker_id=worker_id),
                )
            except AutomationActionError as exc:
                failed_at = datetime.now(UTC)
                self._record_failure(execution, exc.code, failed_at, source="action")
                execution.last_error_code = exc.code
                if exc.retryable and execution.attempt_count < MAX_ATTEMPTS:
                    execution.status = AutomationExecutionStatus.PENDING.value
                    execution.scheduled_for = now + timedelta(
                        seconds=RETRY_DELAYS[execution.attempt_count - 1]
                    )
                    execution.terminal_failure = False
                    logger.warning(
                        "automation.execution.retry_scheduled",
                        extra=self._log_context(execution, worker_id=worker_id),
                    )
                else:
                    execution.status = AutomationExecutionStatus.FAILED.value
                    execution.completed_at = failed_at
                    execution.terminal_failure = True
                    logger.error(
                        "automation.execution.terminal_failure",
                        extra=self._log_context(execution, worker_id=worker_id),
                    )
            execution.claimed_by_worker_id = None
            await self.session.commit()
            processed += 1
        return processed

    async def run_once(
        self,
        *,
        batch_size: int = 20,
        stale_seconds: int | None = None,
        now=None,
        worker_id: str = "automation-worker",
        stop_event=None,
    ) -> tuple[int, int]:
        settings = get_settings()
        stale_seconds = stale_seconds or settings.AUTOMATION_EXECUTION_STALE_SECONDS
        await self.recover_stale_executions(
            stale_seconds=stale_seconds,
            batch_size=batch_size,
            now=now,
            worker_id=worker_id,
        )
        evaluated = await self.evaluate_events(batch_size=batch_size, now=now)
        executed = await self.run_executions(
            batch_size=batch_size,
            now=now,
            worker_id=worker_id,
            stop_event=stop_event,
        )
        return evaluated, executed

    async def record_worker_heartbeat(
        self,
        worker_id: str,
        state: AutomationWorkerState,
        *,
        started_at=None,
        successful_poll: bool = False,
        build_identifier: str | None = None,
        now=None,
    ) -> None:
        now = now or datetime.now(UTC)
        statement = insert(AutomationWorkerHeartbeat).values(
            id=uuid.uuid4(),
            worker_id=worker_id,
            state=state.value,
            started_at=started_at or now,
            last_heartbeat_at=now,
            last_successful_poll_at=now if successful_poll else None,
            build_identifier=build_identifier,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["worker_id"],
                set_={
                    "state": statement.excluded.state,
                    "last_heartbeat_at": statement.excluded.last_heartbeat_at,
                    "last_successful_poll_at": func.coalesce(
                        statement.excluded.last_successful_poll_at,
                        AutomationWorkerHeartbeat.last_successful_poll_at,
                    ),
                    "build_identifier": func.coalesce(
                        statement.excluded.build_identifier,
                        AutomationWorkerHeartbeat.build_identifier,
                    ),
                    "updated_at": now,
                },
            )
        )
        await self.session.commit()

    async def operational_status(self, workspace_id, *, now=None) -> dict:
        now = now or datetime.now(UTC)
        settings = get_settings()
        execution_stale_before = now - timedelta(
            seconds=settings.AUTOMATION_EXECUTION_STALE_SECONDS
        )
        worker_stale_before = now - timedelta(
            seconds=settings.AUTOMATION_WORKER_STALE_SECONDS
        )
        recent_since = now - timedelta(hours=24)
        metrics = (
            await self.session.execute(
                select(
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.PENDING.value,
                        AutomationExecution.scheduled_for <= now,
                    )
                    .label("pending"),
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.PENDING.value,
                        AutomationExecution.scheduled_for > now,
                    )
                    .label("scheduled"),
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.RUNNING.value
                    )
                    .label("running"),
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.SUCCEEDED.value
                    )
                    .label("succeeded"),
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.FAILED.value
                    )
                    .label("failed"),
                    func.count(AutomationExecution.id)
                    .filter(AutomationExecution.terminal_failure.is_(True))
                    .label("terminal_failed"),
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.PENDING.value,
                        AutomationExecution.last_error_code.is_not(None),
                    )
                    .label("retry_pending"),
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.RUNNING.value,
                        AutomationExecution.started_at <= execution_stale_before,
                    )
                    .label("stale_running"),
                ).where(AutomationExecution.workspace_id == workspace_id)
            )
        ).one()
        oldest_pending = await self.session.scalar(
            select(func.min(AutomationExecution.scheduled_for)).where(
                AutomationExecution.workspace_id == workspace_id,
                AutomationExecution.status == AutomationExecutionStatus.PENDING.value,
                AutomationExecution.scheduled_for <= now,
            )
        )
        next_scheduled = await self.session.scalar(
            select(func.min(AutomationExecution.scheduled_for)).where(
                AutomationExecution.workspace_id == workspace_id,
                AutomationExecution.status == AutomationExecutionStatus.PENDING.value,
                AutomationExecution.scheduled_for > now,
            )
        )
        recent = (
            await self.session.execute(
                select(
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.SUCCEEDED.value
                    )
                    .label("succeeded"),
                    func.count(AutomationExecution.id)
                    .filter(
                        AutomationExecution.status
                        == AutomationExecutionStatus.FAILED.value
                    )
                    .label("failed"),
                ).where(
                    AutomationExecution.workspace_id == workspace_id,
                    AutomationExecution.completed_at >= recent_since,
                )
            )
        ).one()
        heartbeat = await self.session.scalar(
            select(AutomationWorkerHeartbeat).order_by(
                AutomationWorkerHeartbeat.last_heartbeat_at.desc()
            )
        )
        if heartbeat is None or heartbeat.state != AutomationWorkerState.RUNNING.value:
            worker_health = "NOT_RUNNING"
        elif heartbeat.last_heartbeat_at <= worker_stale_before:
            worker_health = "STALE"
        else:
            worker_health = "HEALTHY"
        oldest_pending_age = (
            max(0, int((now - oldest_pending).total_seconds()))
            if oldest_pending
            else None
        )
        completed_recent = int(recent.succeeded) + int(recent.failed)
        success_rate = (
            round((int(recent.succeeded) / completed_recent) * 100, 2)
            if completed_recent
            else None
        )
        queue = {
            key: int(getattr(metrics, key))
            for key in (
                "pending",
                "scheduled",
                "running",
                "succeeded",
                "failed",
                "terminal_failed",
                "retry_pending",
                "stale_running",
            )
        }
        alerts: list[str] = []
        if worker_health == "STALE":
            alerts.append("WORKER_STALE")
        elif worker_health == "NOT_RUNNING":
            alerts.append("WORKER_NOT_RUNNING")
        if (
            queue["pending"] + queue["scheduled"]
            >= settings.AUTOMATION_BACKLOG_ALERT_COUNT
        ):
            alerts.append("QUEUE_BACKLOG_HIGH")
        if (
            oldest_pending_age is not None
            and oldest_pending_age
            >= settings.AUTOMATION_BACKLOG_ALERT_THRESHOLD_SECONDS
        ):
            alerts.append("OLDEST_PENDING_TOO_OLD")
        if queue["terminal_failed"]:
            alerts.append("TERMINAL_FAILURES_PRESENT")
        if queue["stale_running"]:
            alerts.append("STALE_RUNNING_PRESENT")
        failures = list(
            await self.session.scalars(
                select(AutomationExecution)
                .where(
                    AutomationExecution.workspace_id == workspace_id,
                    AutomationExecution.status
                    == AutomationExecutionStatus.FAILED.value,
                )
                .order_by(AutomationExecution.completed_at.desc())
                .limit(10)
            )
        )
        return {
            "worker": {
                "health": worker_health,
                "worker_id": heartbeat.worker_id if heartbeat else None,
                "state": heartbeat.state if heartbeat else None,
                "started_at": heartbeat.started_at if heartbeat else None,
                "last_heartbeat_at": heartbeat.last_heartbeat_at if heartbeat else None,
                "last_successful_poll_at": (
                    heartbeat.last_successful_poll_at if heartbeat else None
                ),
                "build_identifier": heartbeat.build_identifier if heartbeat else None,
            },
            "queue": queue,
            "oldest_pending_age_seconds": oldest_pending_age,
            "next_scheduled_execution": next_scheduled,
            "recent_success_rate": success_rate,
            "recent_failures": [
                AutomationExecutionResponse.model_validate(item).model_dump(mode="json")
                for item in failures
            ],
            "alerts": alerts,
            "timestamp": now,
        }

    async def retry_failed_execution(self, workspace_id, execution_id, *, now=None):
        now = now or datetime.now(UTC)
        execution = await self.session.scalar(
            select(AutomationExecution)
            .where(
                AutomationExecution.workspace_id == workspace_id,
                AutomationExecution.id == execution_id,
                AutomationExecution.status == AutomationExecutionStatus.FAILED.value,
            )
            .with_for_update()
        )
        if execution is None:
            exists = await self.session.scalar(
                select(AutomationExecution.id).where(
                    AutomationExecution.workspace_id == workspace_id,
                    AutomationExecution.id == execution_id,
                )
            )
            if exists is None:
                raise NotFoundError("Automation execution not found")
            raise AutomationExecutionStateError()
        execution.status = AutomationExecutionStatus.PENDING.value
        execution.scheduled_for = now
        execution.started_at = None
        execution.completed_at = None
        execution.attempt_count = 0
        execution.manual_retry_count += 1
        execution.last_error_code = None
        execution.terminal_failure = False
        execution.claimed_by_worker_id = None
        await self.session.commit()
        await self.session.refresh(execution)
        logger.info(
            "automation.execution.manual_retry",
            extra=self._log_context(execution),
        )
        return AutomationExecutionResponse.model_validate(execution)

    async def get_execution(self, workspace_id, execution_id):
        item = await self.session.scalar(
            select(AutomationExecution).where(
                AutomationExecution.workspace_id == workspace_id,
                AutomationExecution.id == execution_id,
            )
        )
        if item is None:
            raise NotFoundError("Automation execution not found")
        return AutomationExecutionResponse.model_validate(item)

    async def _execute(self, execution: AutomationExecution) -> None:
        definition = await self.session.get(
            AutomationDefinition, execution.automation_id
        )
        event = await self.session.get(DomainEventOutbox, execution.event_id)
        if (
            not definition
            or not event
            or definition.workspace_id != execution.workspace_id
        ):
            raise AutomationActionError("AUTOMATION_CONTEXT_INVALID")
        if definition.action_type == "internal.notification":
            await self._notify(execution, definition, event)
            return
        if definition.action_type == "customer.message":
            await self._customer_message(execution, definition, event)
            return
        raise AutomationActionError("ACTION_NOT_SUPPORTED")

    async def _release_claims(self, executions, *, now, worker_id: str) -> None:
        for execution in executions:
            if (
                execution.status == AutomationExecutionStatus.RUNNING.value
                and execution.claimed_by_worker_id == worker_id
            ):
                execution.status = AutomationExecutionStatus.PENDING.value
                execution.scheduled_for = now
                execution.started_at = None
                execution.claimed_by_worker_id = None
                logger.info(
                    "automation.execution.released_on_shutdown",
                    extra=self._log_context(execution, worker_id=worker_id),
                )
        await self.session.commit()

    @staticmethod
    def _record_failure(execution, error_code: str, occurred_at, *, source: str):
        history = list(execution.failure_history or [])
        history.append(
            {
                "error_code": error_code,
                "attempt": execution.attempt_count,
                "occurred_at": occurred_at.isoformat(),
                "source": source,
            }
        )
        execution.failure_history = history[-20:]

    @staticmethod
    def _log_context(execution, *, worker_id: str | None = None) -> dict:
        return {
            "workspace_id": str(execution.workspace_id),
            "automation_id": str(execution.automation_id),
            "execution_id": str(execution.id),
            "event_id": str(execution.event_id),
            "worker_id": worker_id or execution.claimed_by_worker_id,
            "attempt": execution.attempt_count,
        }

    async def _notify(self, execution, definition, event) -> None:
        config = definition.action_config
        recipients = await NotificationService(self.session).administrative_recipients(
            execution.workspace_id
        )
        try:
            notification_type = NotificationType(
                config.get("notification_type", NotificationType.ACTION_CREATED.value)
            )
        except ValueError as exc:
            raise AutomationActionError("NOTIFICATION_TYPE_INVALID") from exc
        await NotificationService(self.session).create_for_recipients(
            execution.workspace_id,
            recipients,
            type=notification_type,
            title=self._render(config["title"], event.payload),
            body=self._render(config["body"], event.payload),
            entity_type=NotificationEntityType.ACTION,
            entity_id=event.aggregate_id,
            deduplication_key=execution.effect_key,
        )

    async def _customer_message(self, execution, definition, event) -> None:
        conversation_id = event.payload.get("conversation_id")
        if not conversation_id:
            raise AutomationActionError("CONVERSATION_REQUIRED")
        conversation = await self.session.scalar(
            select(Conversation).where(
                Conversation.workspace_id == execution.workspace_id,
                Conversation.id == uuid.UUID(conversation_id),
            )
        )
        if not conversation or not conversation.channel_connection_id:
            raise AutomationActionError("EXTERNAL_CHANNEL_REQUIRED")
        message = await self.session.scalar(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.external_message_id == execution.effect_key,
            )
        )
        if message is None:
            try:
                async with self.session.begin_nested():
                    message = Message(
                        conversation_id=conversation.id,
                        sender_type=SenderType.SYSTEM,
                        content=self._render(
                            definition.action_config["template"], event.payload
                        ),
                        message_type=MessageType.TEXT,
                        extra_metadata={"automation_execution_id": str(execution.id)},
                        external_message_id=execution.effect_key,
                    )
                    self.session.add(message)
                    await self.session.flush()
            except IntegrityError:
                message = await self.session.scalar(
                    select(Message).where(
                        Message.conversation_id == conversation.id,
                        Message.external_message_id == execution.effect_key,
                    )
                )
        delivery = await ChannelDeliveryService(
            self.session, provider_factory=self.channel_provider_factory
        ).dispatch(conversation, message)
        if delivery.status.value != "SENT":
            # Existing channel delivery rows truthfully prevent an unsafe resend.
            raise AutomationActionError(delivery.last_error_code or "DELIVERY_FAILED")

    async def _scheduled_for(self, definition, event):
        mode = AutomationScheduleMode(definition.schedule_mode)
        if mode is AutomationScheduleMode.IMMEDIATE:
            return event.occurred_at
        if mode is AutomationScheduleMode.DELAY_AFTER_EVENT:
            return event.occurred_at + timedelta(
                seconds=definition.schedule_config["delay_seconds"]
            )
        field_value = event.payload.get(definition.schedule_config["date_field"])
        property_id = event.payload.get("property_id")
        if not field_value or not property_id:
            raise AutomationValidationError("Scheduled event data is incomplete")
        prop = await self.session.scalar(
            select(Property).where(
                Property.workspace_id == event.workspace_id,
                Property.id == uuid.UUID(property_id),
            )
        )
        if prop is None:
            raise AutomationValidationError("Scheduled property was not found")
        day = datetime.fromisoformat(field_value).date()
        hour, minute = map(int, definition.schedule_config["local_time"].split(":"))
        local = datetime.combine(day, time(hour, minute), ZoneInfo(prop.timezone))
        offset = definition.schedule_config["offset_seconds"]
        if mode is AutomationScheduleMode.BEFORE_DATE_FIELD:
            offset = -abs(offset)
        else:
            offset = abs(offset)
        return (local + timedelta(seconds=offset)).astimezone(UTC)

    @staticmethod
    def _matches(raw_conditions, payload) -> bool:
        for raw in raw_conditions:
            condition = AutomationCondition.model_validate(raw)
            actual = payload.get(condition.field)
            expected = condition.value
            if condition.operator in {ConditionOperator.GTE, ConditionOperator.LTE}:
                try:
                    actual, expected = Decimal(str(actual)), Decimal(str(expected))
                except (InvalidOperation, TypeError) as exc:
                    raise AutomationValidationError(
                        "Numeric condition data is invalid"
                    ) from exc
            if condition.operator is ConditionOperator.EQ:
                matched = actual == expected
            elif condition.operator is ConditionOperator.NE:
                matched = actual != expected
            elif condition.operator is ConditionOperator.IN:
                matched = actual in expected
            elif condition.operator is ConditionOperator.GTE:
                matched = actual >= expected
            else:
                matched = actual <= expected
            if not matched:
                return False
        return True

    @staticmethod
    def _render(template: str, payload: dict) -> str:
        validate_template(template)
        return re.sub(
            r"{{\s*([a-z_][a-z0-9_]*)\s*}}",
            lambda match: str(payload.get(match.group(1)) or ""),
            template,
        )
