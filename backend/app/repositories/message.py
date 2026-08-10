"""Message repository."""

import uuid

from sqlalchemy import func, select

from app.models.message import Message
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def get_external(self, conversation_id: uuid.UUID, external_id: str):
        return await self.session.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.external_message_id == external_id,
            )
        )

    async def list_for_conversation(
        self, conversation_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        base = select(Message).where(Message.conversation_id == conversation_id)

        total = await self.session.scalar(
            select(func.count()).select_from(base.subquery())
        )

        stmt = base.order_by(Message.created_at.asc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total or 0)
