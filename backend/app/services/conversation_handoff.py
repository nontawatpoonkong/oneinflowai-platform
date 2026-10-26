"""Workspace-safe conversation handoff and assignment transitions."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.conversation import ConversationMode, HandoffReason
from app.models.notification import NotificationEntityType, NotificationType
from app.models.workspace_member import WorkspaceMember
from app.services.conversation import ConversationService
from app.services.notification import NotificationService
from app.services.workspace_capability import WorkspaceCapability

# Conversation notices may only reach people who can open the conversation.
CONVERSATION_FOLLOW_UP = frozenset({WorkspaceCapability.CONVERSATION_READ})


class ConversationAssignmentError(AppError):
    status_code = 422
    code = "INVALID_CONVERSATION_ASSIGNEE"
    message = "Assignee must be a member of this workspace"


class ConversationHandoffService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationService(session)
        self.notifications = NotificationService(session)

    async def request_handoff(
        self,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reason: HandoffReason,
        *,
        actor_user_id: uuid.UUID | None = None,
        deduplication_key: str,
        commit: bool = True,
    ):
        conversation = await self.conversations.get_conversation(
            workspace_id, conversation_id
        )
        first_request = conversation.handoff_requested_at is None
        conversation.ai_mode = ConversationMode.HUMAN
        conversation.handoff_reason = reason
        conversation.handoff_requested_at = (
            conversation.handoff_requested_at or datetime.now(UTC)
        )
        conversation.needs_attention = True
        if actor_user_id:
            conversation.taken_over_by = actor_user_id
            conversation.taken_over_at = datetime.now(UTC)
        recipients = await self.notifications.assignee_or_administrators(
            workspace_id, conversation.assigned_user_id, CONVERSATION_FOLLOW_UP
        )
        await self.notifications.create_for_recipients(
            workspace_id,
            recipients,
            type=NotificationType.CONVERSATION_HANDOFF,
            title="Conversation needs human attention",
            body="A customer conversation was handed off for staff review.",
            entity_type=NotificationEntityType.CONVERSATION,
            entity_id=conversation.id,
            deduplication_key=deduplication_key,
        )
        if commit:
            await self.session.commit()
            await self.session.refresh(conversation)
        return conversation, first_request

    async def assign(self, workspace_id, conversation_id, assignee_id, actor_user_id):
        member = await self.session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == assignee_id,
            )
        )
        if not member:
            raise ConversationAssignmentError()
        # Refused before any change or notice: the assignee must be able to
        # read the conversation they are given.
        if not await self.notifications.may_follow_up(
            workspace_id, assignee_id, CONVERSATION_FOLLOW_UP
        ):
            raise ConversationAssignmentError(
                "Assignee needs the conversation.read permission"
            )
        conversation = await self.conversations.get_conversation(
            workspace_id, conversation_id
        )
        conversation.assigned_user_id = assignee_id
        conversation.assigned_at = datetime.now(UTC)
        conversation.needs_attention = True
        await self.notifications.create_for_recipients(
            workspace_id,
            [assignee_id],
            type=NotificationType.CONVERSATION_ASSIGNED,
            title="Conversation assigned to you",
            body="Open the conversation to review the customer request.",
            entity_type=NotificationEntityType.CONVERSATION,
            entity_id=conversation.id,
            deduplication_key=f"conversation-assigned:{conversation.id}:{assignee_id}",
        )
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def return_to_ai(self, workspace_id, conversation_id, actor_user_id):
        conversation = await self.conversations.get_conversation(
            workspace_id, conversation_id
        )
        conversation.ai_mode = ConversationMode.AUTO
        conversation.handoff_reason = None
        conversation.handoff_requested_at = None
        conversation.needs_attention = False
        conversation.taken_over_by = None
        conversation.taken_over_at = None
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def unassign(self, workspace_id, conversation_id):
        conversation = await self.conversations.get_conversation(
            workspace_id, conversation_id
        )
        conversation.assigned_user_id = None
        conversation.assigned_at = None
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation
