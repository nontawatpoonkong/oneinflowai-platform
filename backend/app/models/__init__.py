"""ORM models.

Importing this package registers all tables on ``Base.metadata`` (used by
Alembic autogenerate and by test schema creation).
"""

from app.models.conversation import Conversation, ConversationStatus
from app.models.customer import Customer, CustomerStatus
from app.models.customer_identity import CustomerIdentity
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
)
from app.models.knowledge_document_content import KnowledgeDocumentContent
from app.models.message import Message, MessageType, SenderType
from app.models.password_reset_session import PasswordResetSession
from app.models.user import User
from app.models.verification_challenge import (
    VerificationChallenge,
    VerificationPurpose,
)
from app.models.webchat_session import WebChatSession
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole

__all__ = [
    "Conversation",
    "ConversationStatus",
    "Customer",
    "CustomerIdentity",
    "CustomerStatus",
    "Message",
    "KnowledgeDocument",
    "KnowledgeDocumentStatus",
    "KnowledgeDocumentContent",
    "KnowledgeChunk",
    "KnowledgeSourceType",
    "MessageType",
    "PasswordResetSession",
    "SenderType",
    "User",
    "VerificationChallenge",
    "VerificationPurpose",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceRole",
    "WebChatSession",
]
