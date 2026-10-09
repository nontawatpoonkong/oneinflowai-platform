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
from app.models.ai_tool import (
    AIConversationState,
    AIToolAction,
    AIToolActionStatus,
    AIToolAuditEvent,
    AIToolAuditEventType,
    AIToolClassification,
)
from app.models.automation import (
    AutomationActionType,
    AutomationDefinition,
    AutomationExecution,
    AutomationExecutionStatus,
    AutomationScheduleMode,
    AutomationWorkerHeartbeat,
    AutomationWorkerState,
    DomainEventOutbox,
    OutboxState,
)
from app.models.booking import (
    Booking,
    BookingEvent,
    BookingEventType,
    BookingItem,
    BookingStatus,
)
from app.models.channel import (
    ChannelConnection,
    ChannelConnectionStatus,
    ChannelDeliveryStatus,
    ChannelMessageDelivery,
)
from app.models.conversation import Conversation, ConversationStatus, HandoffReason
from app.models.conversation_read_state import ConversationReadState
from app.models.crm import (
    CustomerCRMEvent,
    CustomerCRMEventType,
    CustomerNote,
    CustomerPreference,
    CustomerPreferenceKey,
    CustomerPreferenceSource,
    CustomerTag,
    CustomerTagAssignment,
)
from app.models.customer import Customer, CustomerStatus
from app.models.customer_identity import CustomerIdentity
from app.models.hotel import InventoryDate, Property, RatePlan, RoomType
from app.models.housekeeping import (
    HousekeepingEvent,
    HousekeepingEventType,
    HousekeepingPriority,
    HousekeepingTask,
    HousekeepingTaskStatus,
    RoomReadinessOverrideEvent,
)
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
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentDestination,
    PaymentEvidence,
    PaymentStatus,
    PaymentVerification,
    VerificationStatus,
)
from app.models.stay import (
    HotelRoom,
    RoomOperationalStatus,
    RoomReadinessStatus,
    Stay,
    StayEvent,
    StayEventType,
    StayRoomAssignment,
    StayStatus,
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
    "AIConversationState",
    "AIToolAction",
    "AIToolActionStatus",
    "AIToolAuditEvent",
    "AIToolAuditEventType",
    "AIToolClassification",
    "AutomationActionType",
    "AutomationDefinition",
    "AutomationExecution",
    "AutomationExecutionStatus",
    "AutomationScheduleMode",
    "AutomationWorkerHeartbeat",
    "AutomationWorkerState",
    "DomainEventOutbox",
    "OutboxState",
    "Booking",
    "BookingEvent",
    "BookingEventType",
    "BookingItem",
    "BookingStatus",
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
    "CustomerCRMEvent",
    "CustomerCRMEventType",
    "CustomerIdentity",
    "CustomerNote",
    "CustomerPreference",
    "CustomerPreferenceKey",
    "CustomerPreferenceSource",
    "CustomerStatus",
    "CustomerTag",
    "CustomerTagAssignment",
    "Message",
    "KnowledgeDocument",
    "InventoryDate",
    "Property",
    "RatePlan",
    "RoomType",
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
    "PaymentApplicationReason",
    "PaymentApplicationStatus",
    "PaymentDestination",
    "PaymentEvidence",
    "PaymentStatus",
    "PaymentVerification",
    "HotelRoom",
    "HousekeepingEvent",
    "HousekeepingEventType",
    "HousekeepingPriority",
    "HousekeepingTask",
    "HousekeepingTaskStatus",
    "RoomReadinessOverrideEvent",
    "RoomOperationalStatus",
    "RoomReadinessStatus",
    "Stay",
    "StayEvent",
    "StayEventType",
    "StayRoomAssignment",
    "StayStatus",
    "PlanEntitlement",
    "VerificationStatus",
    "SenderType",
    "SaaSPlan",
    "SaaSUsageRecord",
    "User",
    "VerificationChallenge",
    "VerificationPurpose",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceRole",
    "WorkspaceSubscription",
    "WebChatSession",
]
from app.models.billing import (
    PlanEntitlement,
    SaaSPlan,
    SaaSUsageRecord,
    WorkspaceSubscription,
)
