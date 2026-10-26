"""Append-only global audit and privacy-bounded usage ingestion services."""

import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_log_context, get_request_id
from app.models.audit import (
    AuditActorType,
    AuditArea,
    AuditResult,
    ProductUsageEvent,
    WorkspaceAuditEvent,
)
from app.models.user import User
from app.schemas.audit import ProductUsageEventCreate

_SENSITIVE_FRAGMENTS = frozenset(
    {
        "password",
        "otp",
        "token",
        "secret",
        "credential",
        "authorization",
        "cookie",
        "prompt",
        "message_body",
        "document_content",
        "payment_evidence",
        "bank_payload",
        "card",
        "join_code",
    }
)
_MAX_METADATA_BYTES = 4096


def current_actor_user_id() -> uuid.UUID | None:
    """Return the authenticated request actor without accepting client identity."""

    value = get_log_context().get("user_id")
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None


def safe_audit_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    """Validate deliberately small metadata; reject secret-shaped keys."""

    value = value or {}
    if len(value) > 20:
        raise ValueError("Audit metadata supports at most 20 fields")

    def reject_sensitive_keys(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested_value in item.items():
                normalized = str(key).lower()
                if any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS):
                    raise ValueError(
                        f"Sensitive audit metadata key is not allowed: {key}"
                    )
                reject_sensitive_keys(nested_value)
        elif isinstance(item, list):
            for nested_value in item:
                reject_sensitive_keys(nested_value)

    reject_sensitive_keys(value)
    try:
        encoded = json.dumps(value, default=str, separators=(",", ":")).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("Audit metadata must be JSON serializable") from exc
    if len(encoded) > _MAX_METADATA_BYTES:
        raise ValueError("Audit metadata exceeds the safe size limit")
    return value


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def record(
        self,
        *,
        workspace_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        actor_type: AuditActorType,
        action: str,
        area: AuditArea,
        resource_type: str,
        resource_id: uuid.UUID | None = None,
        result: AuditResult = AuditResult.SUCCESS,
        route: str | None = None,
        request_method: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> WorkspaceAuditEvent:
        item = WorkspaceAuditEvent(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type.value,
            action=action,
            area=area.value,
            resource_type=resource_type,
            resource_id=resource_id,
            route=route,
            request_method=request_method,
            result=result.value,
            correlation_id=get_request_id(),
            safe_metadata=safe_audit_metadata(metadata),
            occurred_at=occurred_at or datetime.now(UTC),
        )
        self.session.add(item)
        return item

    async def list_events(
        self,
        *,
        workspace_id: uuid.UUID,
        page: int,
        page_size: int,
        actor_user_id: uuid.UUID | None = None,
        action: str | None = None,
        area: str | None = None,
        resource_type: str | None = None,
        result: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        filters = [WorkspaceAuditEvent.workspace_id == workspace_id]
        if actor_user_id:
            filters.append(WorkspaceAuditEvent.actor_user_id == actor_user_id)
        if action:
            filters.append(WorkspaceAuditEvent.action == action)
        if area:
            filters.append(WorkspaceAuditEvent.area == area)
        if resource_type:
            filters.append(WorkspaceAuditEvent.resource_type == resource_type)
        if result:
            filters.append(WorkspaceAuditEvent.result == result)
        if start_at:
            filters.append(WorkspaceAuditEvent.occurred_at >= start_at)
        if end_at:
            filters.append(WorkspaceAuditEvent.occurred_at < end_at)
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    WorkspaceAuditEvent.action.ilike(term),
                    WorkspaceAuditEvent.resource_type.ilike(term),
                    WorkspaceAuditEvent.route.ilike(term),
                    User.email.ilike(term),
                    User.full_name.ilike(term),
                )
            )
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(WorkspaceAuditEvent)
                .outerjoin(User, User.id == WorkspaceAuditEvent.actor_user_id)
                .where(*filters)
            )
            or 0
        )
        rows = await self.session.execute(
            select(WorkspaceAuditEvent, User)
            .outerjoin(User, User.id == WorkspaceAuditEvent.actor_user_id)
            .where(*filters)
            .order_by(
                WorkspaceAuditEvent.occurred_at.desc(),
                WorkspaceAuditEvent.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [self._response(event, user) for event, user in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": math.ceil(total / page_size) if total else 0,
        }

    async def get_event(
        self, workspace_id: uuid.UUID, event_id: uuid.UUID
    ) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                select(WorkspaceAuditEvent, User)
                .outerjoin(User, User.id == WorkspaceAuditEvent.actor_user_id)
                .where(
                    WorkspaceAuditEvent.workspace_id == workspace_id,
                    WorkspaceAuditEvent.id == event_id,
                )
            )
        ).one_or_none()
        return self._response(*row) if row else None

    @staticmethod
    def _response(event: WorkspaceAuditEvent, user: User | None) -> dict[str, Any]:
        actor_name = "System"
        if user is not None:
            actor_name = user.full_name or user.email
        elif event.actor_type == AuditActorType.AI.value:
            actor_name = "OneInFlowAI"
        elif event.actor_type == AuditActorType.AUTOMATION.value:
            actor_name = "Automation"
        return {
            "id": event.id,
            "actor": {
                "id": event.actor_user_id,
                "type": event.actor_type,
                "name": actor_name,
            },
            "action": event.action,
            "area": event.area,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "route": event.route,
            "request_method": event.request_method,
            "result": event.result,
            "correlation_id": event.correlation_id,
            "safe_metadata": event.safe_metadata,
            "occurred_at": event.occurred_at,
        }


class ProductUsageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ProductUsageEventCreate,
    ) -> ProductUsageEvent:
        now = datetime.now(UTC)
        occurred_at = data.occurred_at.astimezone(UTC)
        if occurred_at > now or occurred_at < now - timedelta(days=366):
            occurred_at = now
        item = ProductUsageEvent(
            workspace_id=workspace_id,
            user_id=user_id,
            session_id=str(data.session_id) if data.session_id else None,
            navigation_id=data.navigation_id,
            event_name=data.event_name,
            page_path=data.page_path,
            feature=data.feature.value,
            safe_properties=data.safe_properties,
            occurred_at=occurred_at,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(item)
                await self.session.flush()
        except IntegrityError:
            existing = await self.session.scalar(
                select(ProductUsageEvent).where(
                    ProductUsageEvent.workspace_id == workspace_id,
                    ProductUsageEvent.user_id == user_id,
                    ProductUsageEvent.event_name == data.event_name,
                    ProductUsageEvent.navigation_id == data.navigation_id,
                )
            )
            if existing is None:
                raise
            return existing
        await self.session.commit()
        await self.session.refresh(item)
        return item
