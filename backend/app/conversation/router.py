"""Conversation and message routes.

Router handles HTTP + serialization only; all logic lives in the services.
Everything is scoped to the caller's current workspace.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.action.router import require_link_access
from app.ai_tools import create_ai_tool_registry
from app.ai_tools.result_access import result_visible, visible_message_metadata
from app.auth.dependencies import get_current_user
from app.core.channels import ChannelType
from app.database.session import get_db
from app.integrations.action_extraction import create_action_field_extraction_provider
from app.models.ai_tool import AIToolAction
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.ai_tool import AIToolActionResponse
from app.schemas.common import SortOrder
from app.schemas.conversation import (
    ConversationAssignRequest,
    ConversationCreate,
    ConversationHandoffRequest,
    ConversationListResponse,
    ConversationResponse,
    ConversationSortField,
    ConversationUpdate,
)
from app.schemas.message import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.schemas.response import success_response
from app.services.ai_tool_orchestration import AIActionOrchestrationService
from app.services.channel_delivery import ChannelDeliveryService
from app.services.conversation import ConversationService
from app.services.conversation_handoff import ConversationHandoffService
from app.services.conversation_read_state import ConversationReadStateService
from app.services.message import MessageService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import require_workspace_capability

router = APIRouter()

_conversation_read = require_workspace_capability(WorkspaceCapability.CONVERSATION_READ)
_conversation_reply = require_workspace_capability(
    WorkspaceCapability.CONVERSATION_REPLY
)
_conversation_handoff = require_workspace_capability(
    WorkspaceCapability.CONVERSATION_HANDOFF
)


def _conversation_data(conversation: Conversation) -> dict:
    return ConversationResponse.model_validate(conversation).model_dump(mode="json")


def _message_data(message: Message) -> dict:
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_type=message.sender_type,
        sender_id=message.sender_id,
        content=message.content,
        message_type=message.message_type,
        metadata=message.extra_metadata,
        external_message_id=message.external_message_id,
        created_at=message.created_at,
    ).model_dump(mode="json")


# ------------------------------------------------------------ Conversations
@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a conversation")
async def create_conversation(
    payload: ConversationCreate,
    workspace: Workspace = Depends(_conversation_reply),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    # Linking the customer needs guest.read, checked before the id is looked up.
    _, capabilities = await WorkspaceCapabilityService(session).effective(
        workspace.id, user.id
    )
    require_link_access(
        capabilities, customer_id=payload.customer_id, conversation_id=None
    )
    conversation = await ConversationService(session).create_conversation(
        workspace.id, payload
    )
    return success_response(
        data=_conversation_data(conversation), message="Conversation created"
    )


@router.get("", summary="List conversations (search, filter, sort, paginate)")
async def list_conversations(
    workspace: Workspace = Depends(_conversation_read),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, description="Search by subject"),
    status_filter: ConversationStatus | None = Query(default=None, alias="status"),
    customer_id: uuid.UUID | None = Query(default=None),
    channel: ChannelType | None = Query(default=None),
    sort_by: ConversationSortField = Query(
        default=ConversationSortField.LAST_MESSAGE_AT
    ),
    order: SortOrder = Query(default=SortOrder.DESC),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = await ConversationService(session).list_conversations(
        workspace.id,
        search=q,
        status=status_filter,
        customer_id=customer_id,
        channel=channel,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if total else 0
    read_states = ConversationReadStateService(session)
    response_items = []
    for conversation in items:
        item = ConversationResponse.model_validate(conversation)
        item.unread_count = await read_states.unread_count(
            workspace.id, conversation.id, current_user.id
        )
        response_items.append(item)
    data = ConversationListResponse(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
    return success_response(data=data.model_dump(mode="json"), message="OK")


@router.get("/{conversation_id}", summary="Get a conversation by id")
async def get_conversation(
    conversation_id: uuid.UUID,
    workspace: Workspace = Depends(_conversation_read),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await ConversationService(session).get_conversation(
        workspace.id,
        conversation_id,
    )
    data = _conversation_data(conversation)
    data["unread_count"] = await ConversationReadStateService(session).unread_count(
        workspace.id, conversation.id, current_user.id
    )
    return success_response(data=data, message="OK")


@router.patch("/{conversation_id}", summary="Update a conversation")
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    workspace: Workspace = Depends(_conversation_handoff),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await ConversationService(session).update_conversation(
        workspace.id,
        conversation_id,
        payload,
        current_user.id,
    )
    return success_response(
        data=_conversation_data(conversation),
        message="Conversation updated",
    )


# ----------------------------------------------------------------- Messages
@router.post(
    "/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
    summary="Add a message to a conversation",
)
async def create_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    workspace: Workspace = Depends(_conversation_reply),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    trusted_payload = payload.model_copy(
        update={
            "sender_id": current_user.id
            if payload.sender_type.value == "agent"
            else payload.sender_id
        }
    )
    message = await MessageService(session).create_message(
        workspace.id, conversation_id, trusted_payload
    )
    delivery = None
    conversation = await ConversationService(session).get_conversation(
        workspace.id, conversation_id
    )
    if (
        trusted_payload.sender_type.value == "agent"
        and conversation.channel_connection_id is not None
    ):
        delivery = await ChannelDeliveryService(session).dispatch(conversation, message)
    if trusted_payload.sender_type.value == "agent":
        await ConversationReadStateService(session).mark_read(
            workspace.id, conversation_id, current_user.id
        )
    data = _message_data(message)
    if delivery is not None:
        data["delivery"] = {
            "status": delivery.status,
            "provider_message_id": delivery.provider_message_id,
            "last_error_code": delivery.last_error_code,
            "sent_at": delivery.sent_at.isoformat() if delivery.sent_at else None,
        }
    return success_response(data=data, message="Message created")


async def _message_tools(session, workspace_id, conversation_id, items):
    """Tool name and version for AI tool actions referenced by stored results."""

    ids = set()
    for message in items:
        metadata = message.extra_metadata or {}
        if metadata.get("ai_tool_result") is None:
            continue
        try:
            ids.add(uuid.UUID(str(metadata.get("ai_tool_action_id"))))
        except ValueError:
            continue
    if not ids:
        return {}
    rows = await session.execute(
        select(
            AIToolAction.id, AIToolAction.tool_name, AIToolAction.tool_version
        ).where(
            AIToolAction.workspace_id == workspace_id,
            AIToolAction.conversation_id == conversation_id,
            AIToolAction.id.in_(ids),
        )
    )
    return {str(row.id): (row.tool_name, row.tool_version) for row in rows}


@router.get(
    "/{conversation_id}/messages",
    summary="List messages (ordered by created_at ASC, paginated)",
)
async def list_messages(
    conversation_id: uuid.UUID,
    workspace: Workspace = Depends(_conversation_read),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict:
    items, total = await MessageService(session).list_messages(
        workspace.id, conversation_id, page=page, page_size=page_size
    )
    total_pages = (total + page_size - 1) // page_size if total else 0
    tools = await _message_tools(session, workspace.id, conversation_id, items)
    _, capabilities = await WorkspaceCapabilityService(session).effective(
        workspace.id, user.id
    )
    registry = create_ai_tool_registry()
    data = MessageListResponse(
        items=[
            MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                sender_type=m.sender_type,
                sender_id=m.sender_id,
                content=m.content,
                message_type=m.message_type,
                # Messages stored before AI tool results left message metadata
                # still carry them; they follow the result's own capability.
                metadata=visible_message_metadata(
                    m.extra_metadata or {}, tools, registry, capabilities
                ),
                external_message_id=m.external_message_id,
                created_at=m.created_at,
            )
            for m in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
    return success_response(data=data.model_dump(mode="json"), message="OK")


@router.get(
    "/{conversation_id}/ai-actions",
    summary="List structured AI tool actions for a conversation",
)
async def list_ai_actions(
    conversation_id: uuid.UUID,
    workspace: Workspace = Depends(_conversation_read),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = AIActionOrchestrationService(
        session, create_action_field_extraction_provider()
    )
    actions = await service.list_for_conversation(workspace.id, conversation_id)
    # conversation.read lists the tool actions; each typed result needs the
    # capability of its own domain (booking, payment, rooms, promotions).
    _, capabilities = await WorkspaceCapabilityService(session).effective(
        workspace.id, user.id
    )
    return success_response(
        data=[_ai_action(service.registry, item, capabilities) for item in actions],
        message="OK",
    )


def _ai_action(registry, item, capabilities) -> dict:
    data = AIToolActionResponse.model_validate(item)
    if not result_visible(registry, item.tool_name, item.tool_version, capabilities):
        data = data.model_copy(update={"result": None, "result_visible": False})
    return data.model_dump(mode="json")


@router.post("/{conversation_id}/handoff")
async def request_handoff(
    conversation_id: uuid.UUID,
    payload: ConversationHandoffRequest,
    workspace: Workspace = Depends(_conversation_handoff),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    conversation, _ = await ConversationHandoffService(session).request_handoff(
        workspace.id,
        conversation_id,
        payload.reason,
        actor_user_id=user.id,
        deduplication_key=f"manual-handoff:{conversation_id}:{payload.reason}",
    )
    return success_response(_conversation_data(conversation), "Conversation handed off")


@router.post("/{conversation_id}/assign")
async def assign_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationAssignRequest,
    workspace: Workspace = Depends(_conversation_handoff),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    assignee = payload.assigned_user_id or user.id
    conversation = await ConversationHandoffService(session).assign(
        workspace.id, conversation_id, assignee, user.id
    )
    return success_response(_conversation_data(conversation), "Conversation assigned")


@router.post("/{conversation_id}/return-to-ai")
async def return_to_ai(
    conversation_id: uuid.UUID,
    workspace: Workspace = Depends(_conversation_handoff),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    conversation = await ConversationHandoffService(session).return_to_ai(
        workspace.id, conversation_id, user.id
    )
    return success_response(
        _conversation_data(conversation), "Conversation returned to AI"
    )


@router.post("/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: uuid.UUID,
    workspace: Workspace = Depends(_conversation_read),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await ConversationService(session).get_conversation(workspace.id, conversation_id)
    data = await ConversationReadStateService(session).mark_read(
        workspace.id, conversation_id, user.id
    )
    return success_response(data, "Conversation marked read")


@router.post("/{conversation_id}/unassign")
async def unassign_conversation(
    conversation_id: uuid.UUID,
    workspace: Workspace = Depends(_conversation_handoff),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    conversation = await ConversationHandoffService(session).unassign(
        workspace.id, conversation_id
    )
    return success_response(_conversation_data(conversation), "Conversation unassigned")
