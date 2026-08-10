"""Workspace-scoped action collection persistence."""

import uuid

from sqlalchemy import select

from app.models.action_collection import ActionCollectionSession
from app.repositories.base import BaseRepository


class ActionCollectionRepository(BaseRepository[ActionCollectionSession]):
    model = ActionCollectionSession

    async def get(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        *,
        for_update: bool = False,
    ):
        statement = select(ActionCollectionSession).where(
            ActionCollectionSession.workspace_id == workspace_id,
            ActionCollectionSession.id == session_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_active_for_conversation(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID
    ):
        return await self.session.scalar(
            select(ActionCollectionSession)
            .where(
                ActionCollectionSession.workspace_id == workspace_id,
                ActionCollectionSession.conversation_id == conversation_id,
                ActionCollectionSession.status.in_(
                    ("COLLECTING", "AWAITING_CONFIRMATION")
                ),
            )
            .order_by(ActionCollectionSession.updated_at.desc())
            .with_for_update()
            .limit(1)
        )
