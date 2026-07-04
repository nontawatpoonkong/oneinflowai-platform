"""Conversation service.

Business logic for conversations. All operations are workspace-scoped.
A conversation cannot be created without an existing (non-deleted) customer
in the same workspace.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelType
from app.core.exceptions import NotFoundError
from app.models.conversation import Conversation
from app.repositories.conversation import ConversationRepository
from app.repositories.customer import CustomerRepository
from app.schemas.common import SortOrder
from app.schemas.conversation import (
    ConversationCreate,
    ConversationSortField,
    ConversationStatus,
    ConversationUpdate,
)


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.customers = CustomerRepository(session)

    async def create_conversation(
        self, workspace_id: uuid.UUID, data: ConversationCreate
    ) -> Conversation:
        # A conversation cannot exist without a valid customer in this workspace.
        customer = await self.customers.get_active(workspace_id, data.customer_id)
        if customer is None:
            raise NotFoundError("Customer not found in this workspace")

        conversation = Conversation(
            workspace_id=workspace_id,
            customer_id=data.customer_id,
            channel=data.channel,
            status=data.status,
            subject=data.subject,
            assigned_user_id=data.assigned_user_id,
            external_conversation_id=data.external_conversation_id,
        )
        await self.conversations.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_conversation(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation:
        conversation = await self.conversations.get_in_workspace(
            workspace_id, conversation_id
        )
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    async def list_conversations(
        self,
        workspace_id: uuid.UUID,
        *,
        search: str | None,
        status: ConversationStatus | None,
        customer_id: uuid.UUID | None,
        channel: ChannelType | None,
        sort_by: ConversationSortField,
        order: SortOrder,
        page: int,
        page_size: int,
    ) -> tuple[list[Conversation], int]:
        offset = (page - 1) * page_size
        return await self.conversations.list_and_count(
            workspace_id,
            search=search,
            status=status,
            customer_id=customer_id,
            channel=channel,
            sort_by=sort_by,
            order=order,
            limit=page_size,
            offset=offset,
        )

    async def update_conversation(
        self,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        data: ConversationUpdate,
    ) -> Conversation:
        conversation = await self.get_conversation(workspace_id, conversation_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(conversation, field, value)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation
