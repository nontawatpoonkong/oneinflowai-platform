"""Conversation service.

Business logic for conversations. All operations are workspace-scoped.
A conversation cannot be created without an existing (non-deleted) customer
in the same workspace.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelType
from app.core.exceptions import AppError, NotFoundError
from app.models.channel import ChannelConnection
from app.models.conversation import Conversation, ConversationMode
from app.models.workspace_member import WorkspaceMember
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
        connection_id = getattr(data, "channel_connection_id", None)
        if connection_id and not await self.session.scalar(
            select(ChannelConnection.id).where(
                ChannelConnection.id == connection_id,
                ChannelConnection.workspace_id == workspace_id,
            )
        ):
            raise NotFoundError("Channel connection not found")
        if data.assigned_user_id is not None:
            await self._require_assignable(workspace_id, data.assigned_user_id)

        conversation = Conversation(
            workspace_id=workspace_id,
            customer_id=data.customer_id,
            channel=data.channel,
            status=data.status,
            subject=data.subject,
            assigned_user_id=data.assigned_user_id,
            external_conversation_id=data.external_conversation_id,
            channel_connection_id=getattr(data, "channel_connection_id", None),
        )
        await self.conversations.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def _require_assignable(self, workspace_id, user_id) -> None:
        # Same rule as POST /conversations/{id}/assign: the assignee must be a
        # member who can read the conversation.
        from app.services.conversation_handoff import (
            CONVERSATION_FOLLOW_UP,
            ConversationAssignmentError,
        )
        from app.services.notification import NotificationService

        if not await NotificationService(self.session).may_follow_up(
            workspace_id, user_id, CONVERSATION_FOLLOW_UP
        ):
            raise ConversationAssignmentError(
                "Assignee needs the conversation.read permission"
            )

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
        current_user_id: uuid.UUID,
    ) -> Conversation:
        conversation = await self.get_conversation(workspace_id, conversation_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "ai_mode":
                self._apply_ai_mode(conversation, value, current_user_id)
            elif field == "assigned_user_id" and value is not None:
                member = await self.session.scalar(
                    select(WorkspaceMember.id).where(
                        WorkspaceMember.workspace_id == workspace_id,
                        WorkspaceMember.user_id == value,
                    )
                )
                if member is None:
                    raise InvalidConversationAssigneeError()
                conversation.assigned_user_id = value
                conversation.assigned_at = datetime.now(UTC)
            else:
                setattr(conversation, field, value)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    @staticmethod
    def _apply_ai_mode(
        conversation: Conversation,
        mode: ConversationMode,
        current_user_id: uuid.UUID,
    ) -> None:
        conversation.ai_mode = mode
        if mode == ConversationMode.AUTO:
            conversation.taken_over_by = None
            conversation.taken_over_at = None
            return

        conversation.taken_over_by = current_user_id
        conversation.taken_over_at = datetime.now(UTC)


class InvalidConversationAssigneeError(AppError):
    status_code = 422
    code = "INVALID_CONVERSATION_ASSIGNEE"
    message = "Assignee must be a member of this workspace"
