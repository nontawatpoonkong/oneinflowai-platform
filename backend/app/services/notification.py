"""Recipient-scoped, deduplicated in-app notifications."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.notification import (
    Notification,
    NotificationEntityType,
    NotificationType,
)
from app.models.workspace_member import WorkspaceMember, WorkspaceRole


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def administrative_recipients(
        self, workspace_id: uuid.UUID
    ) -> list[uuid.UUID]:
        result = await self.session.scalars(
            select(WorkspaceMember.user_id).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role.in_((WorkspaceRole.OWNER, WorkspaceRole.ADMIN)),
            )
        )
        return list(result)

    async def create_for_recipients(
        self,
        workspace_id: uuid.UUID,
        recipients: list[uuid.UUID],
        *,
        type: NotificationType,
        title: str,
        body: str,
        entity_type: NotificationEntityType,
        entity_id: uuid.UUID,
        deduplication_key: str,
    ) -> None:
        for recipient in set(recipients):
            try:
                async with self.session.begin_nested():
                    self.session.add(
                        Notification(
                            workspace_id=workspace_id,
                            recipient_user_id=recipient,
                            type=type,
                            title=title,
                            body=body,
                            entity_type=entity_type,
                            entity_id=entity_id,
                            deduplication_key=deduplication_key,
                        )
                    )
                    await self.session.flush()
            except IntegrityError:
                continue

    async def list(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, *, limit: int = 30
    ):
        items = list(
            await self.session.scalars(
                select(Notification)
                .where(
                    Notification.workspace_id == workspace_id,
                    Notification.recipient_user_id == user_id,
                )
                .order_by(Notification.created_at.desc())
                .limit(limit)
            )
        )
        unread = await self.unread_count(workspace_id, user_id)
        return items, unread

    async def unread_count(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> int:
        value = await self.session.scalar(
            select(func.count(Notification.id)).where(
                Notification.workspace_id == workspace_id,
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        return int(value or 0)

    async def mark_read(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
    ):
        item = await self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.workspace_id == workspace_id,
                Notification.recipient_user_id == user_id,
            )
        )
        if item is None:
            raise NotFoundError("Notification not found")
        item.is_read = True
        item.read_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def mark_all_read(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.workspace_id == workspace_id,
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        await self.session.commit()
        return result.rowcount or 0
