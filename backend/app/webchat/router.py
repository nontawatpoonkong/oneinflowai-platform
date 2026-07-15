"""Unauthenticated visitor WebChat endpoints authorized by session token."""

import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.message import MessageListResponse, MessageResponse
from app.schemas.response import success_response
from app.schemas.webchat import WebChatMessageCreate, WebChatSessionCreate
from app.services.webchat import WebChatService
from app.webchat.rate_limit import enforce_webchat_rate_limit

router = APIRouter(dependencies=[Depends(enforce_webchat_rate_limit)])


def _message_data(message) -> dict:
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


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: WebChatSessionCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    conversation_id, token = await WebChatService(session).create_session(
        payload,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    return success_response(
        data={"conversation_id": str(conversation_id), "session_token": token},
        message="WebChat session created",
    )


@router.post(
    "/sessions/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: WebChatMessageCreate,
    token: str = Header(alias="X-WebChat-Token", min_length=1),
    session: AsyncSession = Depends(get_db),
) -> dict:
    message = await WebChatService(session).send_message(
        conversation_id, token, payload.content
    )
    return success_response(data=_message_data(message), message="Message created")


@router.get("/sessions/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    token: str = Header(alias="X-WebChat-Token", min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await WebChatService(session).list_messages(
        conversation_id, token, page=page, page_size=page_size
    )
    data = MessageListResponse(
        items=[MessageResponse(**_message_data(item)) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )
    return success_response(data=data.model_dump(mode="json"), message="OK")
