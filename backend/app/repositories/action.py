"""Workspace-scoped fulfillment queue persistence."""

import uuid

from sqlalchemy import func, select

from app.models.action import (
    ActionDefinition,
    ActionEvent,
    ActionPriority,
    ActionRequest,
    ActionRequestStatus,
)
from app.repositories.base import BaseRepository


class ActionDefinitionRepository(BaseRepository[ActionDefinition]):
    model = ActionDefinition

    async def get(self, workspace_id: uuid.UUID, definition_id: uuid.UUID):
        return await self.session.scalar(
            select(ActionDefinition).where(
                ActionDefinition.workspace_id == workspace_id,
                ActionDefinition.id == definition_id,
            )
        )

    async def get_by_key(self, workspace_id: uuid.UUID, key: str):
        return await self.session.scalar(
            select(ActionDefinition).where(
                ActionDefinition.workspace_id == workspace_id,
                ActionDefinition.key == key,
            )
        )

    async def list(self, workspace_id: uuid.UUID):
        result = await self.session.execute(
            select(ActionDefinition)
            .where(ActionDefinition.workspace_id == workspace_id)
            .order_by(ActionDefinition.key)
        )
        return list(result.scalars())


class ActionRequestRepository(BaseRepository[ActionRequest]):
    model = ActionRequest

    async def get(self, workspace_id: uuid.UUID, action_id: uuid.UUID):
        return await self.session.scalar(
            select(ActionRequest).where(
                ActionRequest.workspace_id == workspace_id,
                ActionRequest.id == action_id,
            )
        )

    async def get_idempotent(self, workspace_id: uuid.UUID, key: str):
        return await self.session.scalar(
            select(ActionRequest).where(
                ActionRequest.workspace_id == workspace_id,
                ActionRequest.idempotency_key == key,
            )
        )

    async def list_and_count(
        self,
        workspace_id: uuid.UUID,
        *,
        status: ActionRequestStatus | None,
        priority: ActionPriority | None,
        assigned_to: uuid.UUID | None,
        action_definition_id: uuid.UUID | None,
        conversation_id: uuid.UUID | None,
        page: int,
        page_size: int,
    ):
        stmt = select(ActionRequest).where(ActionRequest.workspace_id == workspace_id)
        for column, value in (
            (ActionRequest.status, status),
            (ActionRequest.priority, priority),
            (ActionRequest.assigned_to_user_id, assigned_to),
            (ActionRequest.action_definition_id, action_definition_id),
            (ActionRequest.conversation_id, conversation_id),
        ):
            if value is not None:
                stmt = stmt.where(column == value)
        total = int(
            await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
            or 0
        )
        result = await self.session.execute(
            stmt.order_by(ActionRequest.created_at.asc(), ActionRequest.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars()), total


class ActionEventRepository(BaseRepository[ActionEvent]):
    model = ActionEvent

    async def list(self, workspace_id: uuid.UUID, action_id: uuid.UUID):
        result = await self.session.execute(
            select(ActionEvent)
            .where(
                ActionEvent.workspace_id == workspace_id,
                ActionEvent.action_request_id == action_id,
            )
            .order_by(ActionEvent.created_at, ActionEvent.id)
        )
        return list(result.scalars())
