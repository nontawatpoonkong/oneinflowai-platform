"""Business fulfillment queue orchestration and lifecycle enforcement."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ActionAssignmentError,
    ActionDefinitionConflictError,
    ActionNotFoundError,
    ActionTransitionError,
    WorkspaceAccessDeniedError,
)
from app.models.action import (
    ActionActorType,
    ActionDefinition,
    ActionEvent,
    ActionEventType,
    ActionRequest,
    ActionRequestStatus,
)
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.notification import NotificationEntityType, NotificationType
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.repositories.action import (
    ActionDefinitionRepository,
    ActionEventRepository,
    ActionRequestRepository,
)
from app.schemas.action import (
    ActionCreate,
    ActionDefinitionCreate,
    ActionDefinitionUpdate,
)
from app.services.action_validation import ActionPayloadValidator
from app.services.notification import NotificationService

_TRANSITIONS = {
    ActionRequestStatus.WAITING: {
        ActionRequestStatus.ASSIGNED,
        ActionRequestStatus.CANCELLED,
    },
    ActionRequestStatus.ASSIGNED: {
        ActionRequestStatus.IN_PROGRESS,
        ActionRequestStatus.CANCELLED,
    },
    ActionRequestStatus.IN_PROGRESS: {
        ActionRequestStatus.COMPLETED,
        ActionRequestStatus.FAILED,
        ActionRequestStatus.CANCELLED,
    },
}


class ActionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.definitions = ActionDefinitionRepository(session)
        self.actions = ActionRequestRepository(session)
        self.events = ActionEventRepository(session)
        self.validator = ActionPayloadValidator()

    async def require_definition_admin(self, workspace_id, user_id) -> None:
        role = await self.session.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if role not in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
            raise WorkspaceAccessDeniedError()

    async def create_definition(self, workspace_id, data: ActionDefinitionCreate):
        if await self.definitions.get_by_key(workspace_id, data.key):
            raise ActionDefinitionConflictError()
        definition = ActionDefinition(
            workspace_id=workspace_id, **data.model_dump(mode="json")
        )
        await self.definitions.add(definition)
        await self.session.commit()
        await self.session.refresh(definition)
        return definition

    async def list_definitions(self, workspace_id):
        return await self.definitions.list(workspace_id)

    async def get_definition(self, workspace_id, definition_id):
        definition = await self.definitions.get(workspace_id, definition_id)
        if not definition:
            raise ActionNotFoundError()
        return definition

    async def update_definition(
        self, workspace_id, definition_id, data: ActionDefinitionUpdate
    ):
        definition = await self.get_definition(workspace_id, definition_id)
        for key, value in data.model_dump(exclude_unset=True, mode="json").items():
            setattr(definition, key, value)
        await self.session.commit()
        await self.session.refresh(definition)
        return definition

    async def create(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None,
        data: ActionCreate,
        *,
        commit: bool = True,
    ):
        definition = await self.get_definition(workspace_id, data.action_definition_id)
        if not definition.is_active:
            raise ActionNotFoundError("Active action definition not found")
        if data.idempotency_key:
            existing = await self.actions.get_idempotent(
                workspace_id, data.idempotency_key
            )
            if existing:
                return existing
        await self._validate_links(workspace_id, data.conversation_id, data.customer_id)
        payload = self.validator.validate(definition, data.payload)
        action = ActionRequest(
            workspace_id=workspace_id,
            action_definition_id=definition.id,
            conversation_id=data.conversation_id,
            customer_id=data.customer_id,
            priority=data.priority,
            payload=payload,
            created_by_type=ActionActorType.HUMAN,
            created_by_user_id=user_id,
            idempotency_key=data.idempotency_key,
        )
        await self.actions.add(action)
        await self.session.flush()
        await self._event(action, ActionEventType.CREATED, user_id)
        notifications = NotificationService(self.session)
        await notifications.create_for_recipients(
            workspace_id,
            await notifications.administrative_recipients(workspace_id),
            type=NotificationType.ACTION_CREATED,
            title="New action requires attention",
            body="A new fulfillment action is ready for staff review.",
            entity_type=NotificationEntityType.ACTION,
            entity_id=action.id,
            deduplication_key=f"action-created:{action.id}",
        )
        if not commit:
            return action
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if data.idempotency_key and (
                existing := await self.actions.get_idempotent(
                    workspace_id, data.idempotency_key
                )
            ):
                return existing
            raise exc
        await self.session.refresh(action)
        return action

    async def get(self, workspace_id, action_id):
        action = await self.actions.get(workspace_id, action_id)
        if not action:
            raise ActionNotFoundError()
        return action

    async def list(self, workspace_id, **filters):
        return await self.actions.list_and_count(workspace_id, **filters)

    async def assign(self, workspace_id, action_id, assigned_user_id, actor_user_id):
        member = await self.session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == assigned_user_id,
            )
        )
        if not member:
            raise ActionAssignmentError()
        action = await self.get(workspace_id, action_id)
        self._transition(action, ActionRequestStatus.ASSIGNED)
        action.assigned_to_user_id = assigned_user_id
        action.assigned_at = datetime.now(UTC)
        await NotificationService(self.session).create_for_recipients(
            workspace_id,
            [assigned_user_id],
            type=NotificationType.ACTION_ASSIGNED,
            title="Action assigned to you",
            body="Open the action queue to review the assigned work.",
            entity_type=NotificationEntityType.ACTION,
            entity_id=action.id,
            deduplication_key=f"action-assigned:{action.id}:{assigned_user_id}",
        )
        return await self._commit_transition(
            action,
            ActionEventType.ASSIGNED,
            actor_user_id,
            {"assigned_to_user_id": str(assigned_user_id)},
        )

    async def transition(self, workspace_id, action_id, target, actor_user_id):
        action = await self.get(workspace_id, action_id)
        self._transition(action, target)
        now = datetime.now(UTC)
        event = {
            ActionRequestStatus.IN_PROGRESS: ActionEventType.STARTED,
            ActionRequestStatus.COMPLETED: ActionEventType.COMPLETED,
            ActionRequestStatus.FAILED: ActionEventType.FAILED,
            ActionRequestStatus.CANCELLED: ActionEventType.CANCELLED,
        }[target]
        if target is ActionRequestStatus.IN_PROGRESS:
            action.started_at = now
        elif target is ActionRequestStatus.COMPLETED:
            action.completed_at = now
        elif target is ActionRequestStatus.CANCELLED:
            action.cancelled_at = now
        return await self._commit_transition(action, event, actor_user_id)

    async def _commit_transition(
        self, action, event_type, actor_user_id, metadata=None
    ):
        await self._event(action, event_type, actor_user_id, metadata)
        await self.session.commit()
        await self.session.refresh(action)
        return action

    @staticmethod
    def _transition(action, target):
        if target not in _TRANSITIONS.get(action.status, set()):
            raise ActionTransitionError(details={"from": action.status, "to": target})
        action.status = target

    async def _event(self, action, event_type, actor_user_id, metadata=None):
        await self.events.add(
            ActionEvent(
                workspace_id=action.workspace_id,
                action_request_id=action.id,
                event_type=event_type,
                actor_user_id=actor_user_id,
                actor_type=ActionActorType.HUMAN,
                event_metadata=metadata or {},
            )
        )

    async def _validate_links(self, workspace_id, conversation_id, customer_id):
        if conversation_id and not await self.session.scalar(
            select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
            )
        ):
            raise ActionNotFoundError("Conversation not found")
        if customer_id and not await self.session.scalar(
            select(Customer.id).where(
                Customer.id == customer_id,
                Customer.workspace_id == workspace_id,
                Customer.deleted_at.is_(None),
            )
        ):
            raise ActionNotFoundError("Customer not found")
