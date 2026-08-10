"""Truthful per-member conversation read cursors and derived unread counts."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_read_state import ConversationReadState
from app.models.message import Message, SenderType


class ConversationReadStateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def unread_count(self, workspace_id, conversation_id, user_id) -> int:
        state = await self.session.scalar(
            select(ConversationReadState).where(
                ConversationReadState.workspace_id == workspace_id,
                ConversationReadState.conversation_id == conversation_id,
                ConversationReadState.user_id == user_id,
            )
        )
        conditions = [
            Message.conversation_id == conversation_id,
            Message.sender_type == SenderType.CUSTOMER,
        ]
        if state:
            conditions.append(Message.created_at > state.last_read_at)
        value = await self.session.scalar(
            select(func.count(Message.id)).where(*conditions)
        )
        return int(value or 0)

    async def mark_read(self, workspace_id, conversation_id, user_id):
        latest = await self.session.scalar(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        now = datetime.now(UTC)
        statement = insert(ConversationReadState).values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            user_id=user_id,
            last_read_message_id=latest.id if latest else None,
            last_read_at=now,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_conversation_read_state_user",
            set_={
                "last_read_message_id": latest.id if latest else None,
                "last_read_at": now,
                "updated_at": now,
            },
        )
        await self.session.execute(statement)
        await self.session.commit()
        return {"unread_count": 0, "last_read_at": now}
