"""WebChat session persistence."""

import uuid

from sqlalchemy import select

from app.models.webchat_session import WebChatSession
from app.repositories.base import BaseRepository


class WebChatSessionRepository(BaseRepository[WebChatSession]):
    model = WebChatSession

    async def get_for_conversation(
        self, conversation_id: uuid.UUID
    ) -> WebChatSession | None:
        result = await self.session.execute(
            select(WebChatSession).where(
                WebChatSession.conversation_id == conversation_id
            )
        )
        return result.scalar_one_or_none()
