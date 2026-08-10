"""Message service.

A message cannot exist without a conversation in the caller's workspace.
Creating a message advances the conversation's ``last_message_at``.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.message import Message, SenderType
from app.models.notification import NotificationEntityType, NotificationType
from app.repositories.conversation import ConversationRepository
from app.repositories.message import MessageRepository
from app.schemas.message import MessageCreate
from app.services.notification import NotificationService


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
        *,
        commit: bool = True,
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
        await self.session.flush()

        conversation.last_message_at = datetime.now(UTC)
        if data.sender_type is SenderType.CUSTOMER:
            conversation.needs_attention = True
            notifications = NotificationService(self.session)
            recipients = (
                [conversation.assigned_user_id]
                if conversation.assigned_user_id
                else await notifications.administrative_recipients(workspace_id)
            )
            await notifications.create_for_recipients(
                workspace_id,
                recipients,
                type=NotificationType.NEW_CUSTOMER_MESSAGE,
                title="New customer message",
                body="A customer conversation has a new message.",
                entity_type=NotificationEntityType.CONVERSATION,
                entity_id=conversation.id,
                deduplication_key=(
                    f"customer-message:{conversation.id}:"
                    f"{data.external_message_id or message.id}"
                ),
            )
        if commit:
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
