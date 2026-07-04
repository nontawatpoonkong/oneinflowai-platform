"""Message service.

A message cannot exist without a conversation in the caller's workspace.
Creating a message advances the conversation's ``last_message_at``.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.message import Message
from app.repositories.conversation import ConversationRepository
from app.repositories.message import MessageRepository
from app.schemas.message import MessageCreate


class MessageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.messages = MessageRepository(session)
        self.conversations = ConversationRepository(session)

    async def _get_conversation_or_404(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID
    ):
        conversation = await self.conversations.get_in_workspace(
            workspace_id, conversation_id
        )
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    async def create_message(
        self,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        data: MessageCreate,
    ) -> Message:
        conversation = await self._get_conversation_or_404(
            workspace_id, conversation_id
        )

        message = Message(
            conversation_id=conversation.id,
            sender_type=data.sender_type,
            sender_id=data.sender_id,
            content=data.content,
            message_type=data.message_type,
            extra_metadata=data.metadata,
            external_message_id=data.external_message_id,
        )
        await self.messages.add(message)

        conversation.last_message_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def list_messages(
        self,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[Message], int]:
        await self._get_conversation_or_404(workspace_id, conversation_id)
        offset = (page - 1) * page_size
        return await self.messages.list_for_conversation(
            conversation_id, limit=page_size, offset=offset
        )
