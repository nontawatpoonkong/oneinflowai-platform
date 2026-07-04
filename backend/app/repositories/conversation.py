"""Conversation repository."""

import uuid

from sqlalchemy import Select, func, or_, select

from app.core.channels import ChannelType
from app.models.conversation import Conversation, ConversationStatus
from app.models.customer import Customer
from app.repositories.base import BaseRepository
from app.schemas.common import SortOrder
from app.schemas.conversation import ConversationSortField

_SORT_COLUMNS = {
    ConversationSortField.LAST_MESSAGE_AT: Conversation.last_message_at,
    ConversationSortField.CREATED_AT: Conversation.created_at,
}


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    def _in_workspace(self, workspace_id: uuid.UUID) -> Select:
        return select(Conversation).where(Conversation.workspace_id == workspace_id)

    async def get_in_workspace(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation | None:
        stmt = self._in_workspace(workspace_id).where(
            Conversation.id == conversation_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_and_count(
        self,
        workspace_id: uuid.UUID,
        *,
        search: str | None,
        status: ConversationStatus | None,
        customer_id: uuid.UUID | None,
        channel: ChannelType | None,
        sort_by: ConversationSortField,
        order: SortOrder,
        limit: int,
        offset: int,
    ) -> tuple[list[Conversation], int]:
        stmt = self._in_workspace(workspace_id)

        if status is not None:
            stmt = stmt.where(Conversation.status == status)
        if customer_id is not None:
            stmt = stmt.where(Conversation.customer_id == customer_id)
        if channel is not None:
            stmt = stmt.where(Conversation.channel == channel)
        if search:
            # Search across the conversation subject and the linked customer's
            # display_name / full_name (1:1 join, no row multiplication).
            pattern = f"%{search}%"
            stmt = stmt.join(
                Customer, Conversation.customer_id == Customer.id
            ).where(
                or_(
                    Conversation.subject.ilike(pattern),
                    Customer.display_name.ilike(pattern),
                    Customer.full_name.ilike(pattern),
                )
            )

        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )

        sort_column = _SORT_COLUMNS[sort_by]
        direction = sort_column.asc() if order == SortOrder.ASC else sort_column.desc()
        stmt = stmt.order_by(direction.nulls_last()).offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total or 0)
