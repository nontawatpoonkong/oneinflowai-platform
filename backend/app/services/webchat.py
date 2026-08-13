"""Public WebChat orchestration and token authorization."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelType
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    WebChatNotConnectedError,
)
from app.models.channel import ChannelConnectionStatus
from app.models.message import Message, SenderType
from app.models.webchat_session import WebChatSession
from app.repositories.webchat_session import WebChatSessionRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.conversation import ConversationCreate
from app.schemas.customer import CustomerCreate
from app.schemas.message import MessageCreate
from app.schemas.webchat import WebChatSessionCreate
from app.services.channel_connection import ChannelConnectionService
from app.services.conversation import ConversationService
from app.services.customer import CustomerService
from app.services.entitlement import EntitlementService
from app.services.message import MessageService


class WebChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sessions = WebChatSessionRepository(session)
        self.workspaces = WorkspaceRepository(session)
        self.settings = get_settings()

    def _expiry(self) -> datetime:
        return datetime.now(UTC) + timedelta(
            days=self.settings.WEBCHAT_SESSION_TTL_DAYS
        )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def hash_ip(self, ip: str | None) -> str | None:
        if not ip:
            return None
        return hmac.new(
            self.settings.WEBCHAT_METADATA_HASH_SECRET.encode(),
            ip.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def create_session(
        self, data: WebChatSessionCreate, *, user_agent: str | None, ip: str | None
    ) -> tuple[uuid.UUID, str]:
        workspace = await self.workspaces.get_by_slug(data.workspace_key)
        if workspace is None:
            raise NotFoundError("Workspace not found")
        await EntitlementService(self.session).require(workspace.id, "channels.webchat")
        connection = await ChannelConnectionService(self.session).get_web(workspace.id)
        if (
            connection is None
            or connection.status is not ChannelConnectionStatus.CONNECTED
        ):
            raise WebChatNotConnectedError()

        # TODO: When verified visitor identity exists, use this flag to enable a
        # carefully scoped merge implementation. Public email/phone is unverified.
        customer = await CustomerService(self.session).create_customer(
            workspace.id,
            CustomerCreate(
                display_name=data.name,
                full_name=data.name,
                email=data.email,
                phone=data.phone,
            ),
        )
        conversation = await ConversationService(self.session).create_conversation(
            workspace.id,
            ConversationCreate(
                customer_id=customer.id,
                channel=ChannelType.WEB,
                channel_connection_id=connection.id,
            ),
        )
        raw_token = secrets.token_urlsafe(32)
        webchat_session = WebChatSession(
            conversation_id=conversation.id,
            token_hash=self._token_hash(raw_token),
            expires_at=self._expiry(),
            user_agent=(user_agent or "")[:512] or None,
            ip_hash=self.hash_ip(ip),
            language=data.language,
            timezone=data.timezone,
            landing_url=data.landing_url,
            referrer=data.referrer,
        )
        await self.sessions.add(webchat_session)
        await self.session.commit()
        return conversation.id, raw_token

    async def authorize(
        self, conversation_id: uuid.UUID, raw_token: str
    ) -> WebChatSession:
        stored = await self.sessions.get_for_conversation(conversation_id)
        candidate = self._token_hash(raw_token)
        if (
            stored is None
            or stored.expires_at <= datetime.now(UTC)
            or not hmac.compare_digest(stored.token_hash, candidate)
        ):
            raise AuthenticationError("Invalid or expired WebChat session")
        return stored

    async def send_message(
        self, conversation_id: uuid.UUID, token: str, content: str
    ) -> Message:
        stored = await self.authorize(conversation_id, token)
        conversation = await ConversationService(self.session).conversations.get_by_id(
            conversation_id
        )
        if conversation is None:
            raise AuthenticationError("Invalid or expired WebChat session")
        message = await MessageService(self.session).create_message(
            conversation.workspace_id,
            conversation_id,
            MessageCreate(sender_type=SenderType.CUSTOMER, content=content),
        )
        stored.expires_at = self._expiry()
        await self.session.commit()
        return message

    async def _conversation_or_unauthorized(self, conversation_id: uuid.UUID):
        conversation = await ConversationService(self.session).conversations.get_by_id(
            conversation_id
        )
        if conversation is None:
            raise AuthenticationError("Invalid or expired WebChat session")
        return conversation

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        token: str,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[Message], int]:
        stored = await self.authorize(conversation_id, token)
        conversation = await ConversationService(self.session).conversations.get_by_id(
            conversation_id
        )
        if conversation is None:
            raise AuthenticationError("Invalid or expired WebChat session")
        result = await MessageService(self.session).list_messages(
            conversation.workspace_id,
            conversation_id,
            page=page,
            page_size=page_size,
        )
        stored.expires_at = self._expiry()
        await self.session.commit()
        return result
