"""Stable v1 automation events written inside source-domain transactions."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.models.automation import DomainEventOutbox, OutboxState


def _json_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


async def emit_domain_event(
    session,
    *,
    workspace_id: uuid.UUID,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    deduplication_key: str,
    occurred_at: datetime | None = None,
) -> None:
    """Insert once without committing; the caller owns the domain transaction."""
    now = occurred_at or datetime.now(UTC)
    safe_payload = {key: _json_value(value) for key, value in payload.items()}
    safe_payload["workspace_id"] = str(workspace_id)
    safe_payload["occurred_at"] = now.isoformat()
    statement = (
        insert(DomainEventOutbox)
        .values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_version=1,
            payload=safe_payload,
            occurred_at=now,
            available_at=now,
            state=OutboxState.PENDING.value,
            attempt_count=0,
            deduplication_key=deduplication_key,
        )
        .on_conflict_do_nothing(index_elements=["workspace_id", "deduplication_key"])
    )
    await session.execute(statement)


async def emit_booking_event(session, booking, event_type: str) -> None:
    await emit_domain_event(
        session,
        workspace_id=booking.workspace_id,
        aggregate_type="booking",
        aggregate_id=booking.id,
        event_type=event_type,
        payload={
            "booking_id": booking.id,
            "property_id": booking.property_id,
            "customer_id": booking.customer_id,
            "conversation_id": booking.conversation_id,
            "customer_name": booking.guest_name,
            "booking_reference": str(booking.id),
            "property_name": booking.property_name_snapshot,
            "check_in": booking.check_in,
            "check_out": booking.check_out,
            "total_amount": booking.total_amount,
            "currency": booking.currency,
        },
        deduplication_key=f"{event_type}:v1:{booking.id}",
    )


async def emit_stay_event(session, stay, event_type: str, *, room_id=None) -> None:
    await emit_domain_event(
        session,
        workspace_id=stay.workspace_id,
        aggregate_type="stay",
        aggregate_id=stay.id,
        event_type=event_type,
        payload={
            "stay_id": stay.id,
            "booking_id": stay.booking_id,
            "property_id": stay.property_id,
            "customer_id": stay.customer_id,
            "room_id": room_id,
            "check_in": stay.planned_check_in_date,
            "check_out": stay.planned_check_out_date,
        },
        deduplication_key=f"{event_type}:v1:{stay.id}",
    )


async def emit_housekeeping_event(session, task, event_type: str) -> None:
    await emit_domain_event(
        session,
        workspace_id=task.workspace_id,
        aggregate_type="housekeeping_task",
        aggregate_id=task.id,
        event_type=event_type,
        payload={
            "task_id": task.id,
            "stay_id": task.stay_id,
            "property_id": task.property_id,
            "room_id": task.room_id,
        },
        deduplication_key=f"{event_type}:v1:{task.id}",
    )
