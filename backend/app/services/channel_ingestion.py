"""Shared LINE/Facebook ingestion into the existing conversation core."""

from sqlalchemy import func, select

from app.models.channel import ChannelConnectionStatus
from app.models.conversation import Conversation, ConversationStatus
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity
from app.services.channel_delivery import ChannelDeliveryService
from app.services.webchat_ai import create_webchat_ai_orchestrator


class ChannelInboundUnavailableError(Exception):
    pass


class ChannelMessageIngestionService:
    def __init__(self, session, qdrant, *, delivery_service=None) -> None:
        self.session = session
        self.orchestrator = create_webchat_ai_orchestrator(session, qdrant)
        self.delivery = delivery_service or ChannelDeliveryService(session)

    async def process(self, connection, inbound):
        if connection.status is not ChannelConnectionStatus.CONNECTED:
            raise ChannelInboundUnavailableError()
        lock_key = f"channel-identity:{connection.id}:{inbound.external_user_id}"
        await self.session.scalar(
            select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0)))
        )
        identity = await self.session.scalar(
            select(CustomerIdentity).where(
                CustomerIdentity.workspace_id == connection.workspace_id,
                CustomerIdentity.channel_connection_id == connection.id,
                CustomerIdentity.external_user_id == inbound.external_user_id,
            )
        )
        if identity is None:
            customer = Customer(
                workspace_id=connection.workspace_id,
                display_name=(inbound.display_name or inbound.external_user_id)[:150],
            )
            self.session.add(customer)
            await self.session.flush()
            identity = CustomerIdentity(
                workspace_id=connection.workspace_id,
                channel_connection_id=connection.id,
                customer_id=customer.id,
                channel=connection.provider,
                external_user_id=inbound.external_user_id,
                external_username=inbound.display_name,
            )
            self.session.add(identity)
            await self.session.flush()
        conversation = await self.session.scalar(
            select(Conversation)
            .where(
                Conversation.workspace_id == connection.workspace_id,
                Conversation.customer_id == identity.customer_id,
                Conversation.channel_connection_id == connection.id,
                Conversation.status.in_(
                    (ConversationStatus.OPEN, ConversationStatus.PENDING)
                ),
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        if conversation is None:
            conversation = Conversation(
                workspace_id=connection.workspace_id,
                customer_id=identity.customer_id,
                channel=connection.provider,
                channel_connection_id=connection.id,
                external_conversation_id=inbound.external_conversation_id,
                status=ConversationStatus.OPEN,
            )
            self.session.add(conversation)
            await self.session.flush()
        customer, assistant, public = await self.orchestrator.process_channel(
            conversation, inbound.external_message_id, inbound.text
        )
        delivery = None
        if assistant is not None:
            delivery = await self.delivery.dispatch(conversation, assistant)
        return customer, assistant, public, delivery
