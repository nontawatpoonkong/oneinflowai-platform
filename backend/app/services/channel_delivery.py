"""External channel outbound dispatch with truthful delivery persistence."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.integrations.channels.facebook import FacebookMessengerChannelProvider
from app.integrations.channels.line import LineChannelProvider
from app.integrations.channels.provider import (
    ChannelOutboundMessage,
    ChannelProviderError,
)
from app.integrations.channels.security import ChannelCredentialSecurityError
from app.models.channel import ChannelDeliveryStatus, ChannelMessageDelivery
from app.models.customer_identity import CustomerIdentity
from app.services.channel_connection import ChannelConnectionService


class ChannelDeliveryService:
    def __init__(self, session, provider_factory=None) -> None:
        self.session = session
        self.connections = ChannelConnectionService(session)
        self.provider_factory = provider_factory or self._provider

    def _provider(self, connection, credentials):
        timeout = get_settings().CHANNEL_PROVIDER_TIMEOUT_SECONDS
        if connection.provider.value == "line":
            return LineChannelProvider(credentials, timeout=timeout)
        return FacebookMessengerChannelProvider(credentials, timeout=timeout)

    async def dispatch(self, conversation, message):
        existing = await self.session.scalar(
            select(ChannelMessageDelivery).where(
                ChannelMessageDelivery.message_id == message.id
            )
        )
        if existing:
            return existing
        delivery = ChannelMessageDelivery(
            workspace_id=conversation.workspace_id,
            message_id=message.id,
            channel_connection_id=conversation.channel_connection_id,
            status=ChannelDeliveryStatus.PENDING,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(delivery)
                await self.session.flush()
        except IntegrityError:
            return await self.session.scalar(
                select(ChannelMessageDelivery).where(
                    ChannelMessageDelivery.message_id == message.id
                )
            )
        connection = await self.connections.get(
            conversation.workspace_id, conversation.channel_connection_id
        )
        identity = await self.session.scalar(
            select(CustomerIdentity).where(
                CustomerIdentity.customer_id == conversation.customer_id,
                CustomerIdentity.channel_connection_id == connection.id,
            )
        )
        try:
            provider = self.provider_factory(
                connection, self.connections.credentials(connection)
            )
            result = await provider.send(
                ChannelOutboundMessage(
                    provider=connection.provider,
                    external_user_id=identity.external_user_id,
                    external_conversation_id=conversation.external_conversation_id,
                    text=message.content,
                )
            )
            delivery.status = ChannelDeliveryStatus.SENT
            delivery.provider_message_id = result.provider_message_id
            delivery.sent_at = datetime.now(UTC)
        except ChannelProviderError as exc:
            delivery.status = ChannelDeliveryStatus.FAILED
            delivery.last_error_code = exc.code.value
        except ChannelCredentialSecurityError:
            delivery.status = ChannelDeliveryStatus.FAILED
            delivery.last_error_code = "AUTHENTICATION_FAILED"
        await self.session.commit()
        await self.session.refresh(delivery)
        return delivery
