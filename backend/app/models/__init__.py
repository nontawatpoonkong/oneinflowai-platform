"""ORM models.

Importing this package registers all tables on ``Base.metadata`` (used by
Alembic autogenerate and by test schema creation).
"""

from app.models.action import (
    ActionActorType,
    ActionDefinition,
    ActionEvent,
    ActionEventType,
    ActionExecutionMode,
    ActionPriority,
    ActionRequest,
    ActionRequestStatus,
)
from app.models.action_collection import (
    ActionCollectionSession,
    ActionCollectionStatus,
)
from app.models.channel import (
    ChannelConnection,
    ChannelConnectionStatus,
    ChannelDeliveryStatus,
    ChannelMessageDelivery,
)
from app.models.conversation import Conversation, ConversationStatus, HandoffReason
from app.models.conversation_read_state import ConversationReadState
from app.models.customer import Customer, CustomerStatus
from app.models.customer_identity import CustomerIdentity
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeIndexStatus,
    KnowledgeSourceType,
)
from app.models.knowledge_document_content import KnowledgeDocumentContent
from app.models.message import Message, MessageType, SenderType
from app.models.notification import (
    Notification,
    NotificationEntityType,
    NotificationType,
)
from app.models.password_reset_session import PasswordResetSession
from app.models.payment import (
    DestinationType,
    Payment,
    PaymentDestination,
    PaymentEvidence,
    PaymentStatus,
    PaymentVerification,
    VerificationStatus,
)
from app.models.user import User
from app.models.verification_challenge import (
    VerificationChallenge,
    VerificationPurpose,
)
from app.models.webchat_session import WebChatSession
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole

__all__ = [
    "ActionActorType",
    "ActionCollectionSession",
    "ActionCollectionStatus",
    "ActionDefinition",
    "ActionEvent",
    "ActionEventType",
    "ActionExecutionMode",
    "ActionPriority",
    "ActionRequest",
    "ActionRequestStatus",
    "ChannelConnection",
    "ChannelConnectionStatus",
    "ChannelDeliveryStatus",
    "ChannelMessageDelivery",
    "Conversation",
    "ConversationStatus",
    "HandoffReason",
    "ConversationReadState",
    "Customer",
    "CustomerIdentity",
    "CustomerStatus",
    "Message",
    "KnowledgeDocument",
    "KnowledgeIndexStatus",
    "KnowledgeDocumentStatus",
    "KnowledgeDocumentContent",
    "KnowledgeChunk",
    "KnowledgeSourceType",
    "MessageType",
    "Notification",
    "NotificationEntityType",
    "NotificationType",
    "PasswordResetSession",
    "DestinationType",
    "Payment",
    "PaymentDestination",
    "PaymentEvidence",
    "PaymentStatus",
    "PaymentVerification",
    "VerificationStatus",
    "SenderType",
    "User",
    "VerificationChallenge",
    "VerificationPurpose",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceRole",
    "WebChatSession",
]
