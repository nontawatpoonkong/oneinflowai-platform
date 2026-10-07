"""Application-level exceptions.

Services raise these; a single handler (registered in `main`) maps them to
the standard error response envelope. This keeps HTTP concerns out of the
service layer.
"""

from typing import Any


class AppError(Exception):
    """Base application error."""

    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "Bad request"

    def __init__(self, message: str | None = None, details: Any | None = None) -> None:
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


class EmailAlreadyExistsError(AppError):
    status_code = 409
    code = "EMAIL_ALREADY_EXISTS"
    message = "A user with this email already exists"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
    message = "Invalid email or password"


class AuthenticationError(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    message = "Not authenticated"


class InactiveUserError(AppError):
    status_code = 403
    code = "INACTIVE_USER"
    message = "User account is inactive"


class EmailNotVerifiedError(AppError):
    status_code = 403
    code = "EMAIL_NOT_VERIFIED"
    message = "Email verification is required"

    def __init__(self) -> None:
        super().__init__(details={"next_action": "VERIFY_EMAIL"})


class InvalidVerificationCodeError(AppError):
    status_code = 400
    code = "INVALID_VERIFICATION_CODE"
    message = "Verification code is invalid or unavailable"


class InvalidPasswordResetCodeError(AppError):
    status_code = 400
    code = "INVALID_PASSWORD_RESET_CODE"
    message = "Password reset code is invalid or unavailable"


class InvalidPasswordResetTokenError(AppError):
    status_code = 400
    code = "INVALID_PASSWORD_RESET_TOKEN"
    message = "Password reset authorization is invalid or expired"


class VerificationConfigurationError(AppError):
    status_code = 500
    code = "VERIFICATION_CONFIGURATION_ERROR"
    message = "Email verification is temporarily unavailable"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found"


class WorkspaceNotFoundError(AppError):
    status_code = 404
    code = "WORKSPACE_NOT_FOUND"
    message = "Workspace not found"


class WorkspaceAccessDeniedError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "You do not have permission to perform this action"


class SlugAlreadyExistsError(AppError):
    status_code = 409
    code = "SLUG_ALREADY_EXISTS"
    message = "A workspace with this name/slug already exists"


class KnowledgeDocumentNotFoundError(AppError):
    status_code = 404
    code = "KNOWLEDGE_DOCUMENT_NOT_FOUND"
    message = "Knowledge document not found"


class InvalidKnowledgeFileError(AppError):
    status_code = 400
    code = "INVALID_KNOWLEDGE_FILE"
    message = "Unsupported or invalid knowledge file"


class KnowledgeFileTooLargeError(AppError):
    status_code = 413
    code = "KNOWLEDGE_FILE_TOO_LARGE"
    message = "Knowledge file exceeds the configured size limit"


class KnowledgeExtractionFailedError(AppError):
    status_code = 422
    code = "KNOWLEDGE_EXTRACTION_FAILED"
    message = "Document text could not be extracted"


class KnowledgeStorageReadError(AppError):
    status_code = 500
    code = "KNOWLEDGE_STORAGE_READ_FAILED"
    message = "Stored document could not be read"


class KnowledgeContentPersistenceError(AppError):
    status_code = 500
    code = "KNOWLEDGE_CONTENT_PERSISTENCE_FAILED"
    message = "Extracted document content could not be saved"


class KnowledgeChunkingFailedError(AppError):
    status_code = 422
    code = "KNOWLEDGE_CHUNKING_FAILED"
    message = "Document content could not be chunked"


class EmbeddingConfigurationError(AppError):
    status_code = 500
    code = "EMBEDDING_CONFIGURATION_ERROR"
    message = "Embedding provider is not configured"


class EmbeddingProviderError(AppError):
    status_code = 502
    code = "EMBEDDING_PROVIDER_ERROR"
    message = "Embedding provider request failed"


class KnowledgeIndexingError(AppError):
    status_code = 502
    code = "KNOWLEDGE_INDEXING_FAILED"
    message = "Knowledge document could not be indexed"


class KnowledgeIndexingNotEligibleError(AppError):
    status_code = 409
    code = "KNOWLEDGE_INDEXING_NOT_ELIGIBLE"
    message = "Knowledge document is not ready for indexing"


class VectorCollectionConfigurationError(AppError):
    status_code = 500
    code = "VECTOR_COLLECTION_CONFIGURATION_ERROR"
    message = "Knowledge vector collection is incompatible"


class KnowledgeRetrievalValidationError(AppError):
    status_code = 422
    code = "KNOWLEDGE_RETRIEVAL_VALIDATION_ERROR"
    message = "Knowledge search request is invalid"


class KnowledgeDocumentNotIndexedError(AppError):
    status_code = 409
    code = "KNOWLEDGE_DOCUMENT_NOT_INDEXED"
    message = "Knowledge document is not indexed"


class KnowledgeRetrievalError(AppError):
    status_code = 502
    code = "KNOWLEDGE_RETRIEVAL_FAILED"
    message = "Knowledge search is temporarily unavailable"


class GenerationConfigurationError(AppError):
    status_code = 500
    code = "GENERATION_CONFIGURATION_ERROR"
    message = "Generation provider is not configured"


class GenerationProviderError(AppError):
    status_code = 502
    code = "GENERATION_PROVIDER_ERROR"
    message = "Answer generation is temporarily unavailable"


class GenerationAuthenticationError(GenerationProviderError):
    code = "GENERATION_AUTHENTICATION_ERROR"


class GenerationRateLimitError(GenerationProviderError):
    code = "GENERATION_RATE_LIMIT_ERROR"


class GenerationTimeoutError(GenerationProviderError):
    status_code = 504
    code = "GENERATION_TIMEOUT"


class GenerationNetworkError(GenerationProviderError):
    code = "GENERATION_NETWORK_ERROR"


class GenerationServerError(GenerationProviderError):
    code = "GENERATION_SERVER_ERROR"


class GenerationMalformedResponseError(GenerationProviderError):
    code = "GENERATION_MALFORMED_RESPONSE"


class GroundingValidationError(AppError):
    status_code = 502
    code = "GROUNDING_VALIDATION_FAILED"
    message = "Generated answer could not be verified against knowledge sources"


class DemoRateLimitExceededError(AppError):
    status_code = 429
    code = "DEMO_RATE_LIMIT_EXCEEDED"
    message = "Public demo request limit exceeded"

    def __init__(self, retry_after_seconds: int) -> None:
        self.headers = {"Retry-After": str(retry_after_seconds)}
        super().__init__(details={"retry_after_seconds": retry_after_seconds})


class DemoRateLimitUnavailableError(AppError):
    status_code = 503
    code = "DEMO_RATE_LIMIT_UNAVAILABLE"
    message = "Public demo is temporarily unavailable"


class SubscriptionRequiredError(AppError):
    status_code = 403
    code = "SUBSCRIPTION_REQUIRED"
    message = "An active subscription is required for this capability"


class EntitlementDeniedError(AppError):
    status_code = 403
    code = "ENTITLEMENT_DENIED"
    message = "The current plan does not include this capability"


class EntitlementQuotaExceededError(AppError):
    status_code = 409
    code = "ENTITLEMENT_QUOTA_EXCEEDED"
    message = "The current plan limit has been reached"


class WebChatNotConnectedError(AppError):
    status_code = 409
    code = "WEBCHAT_NOT_CONNECTED"
    message = "WebChat is not connected for this workspace"


class ActionNotFoundError(AppError):
    status_code = 404
    code = "ACTION_NOT_FOUND"
    message = "Action resource not found"


class ActionDefinitionConflictError(AppError):
    status_code = 409
    code = "ACTION_DEFINITION_CONFLICT"
    message = "Action definition key already exists"


class ActionPayloadValidationError(AppError):
    status_code = 422
    code = "ACTION_PAYLOAD_INVALID"
    message = "Action payload is invalid"


class ActionTransitionError(AppError):
    status_code = 409
    code = "ACTION_TRANSITION_INVALID"
    message = "Action status transition is not allowed"


class ActionAssignmentError(AppError):
    status_code = 422
    code = "ACTION_ASSIGNMENT_INVALID"
    message = "Assigned user is not a member of this workspace"


class PaymentNotFoundError(AppError):
    status_code = 404
    code = "PAYMENT_NOT_FOUND"
    message = "Payment resource not found"


class PaymentValidationError(AppError):
    status_code = 422
    code = "PAYMENT_VALIDATION_ERROR"
    message = "Payment request is invalid"


class PaymentEvidenceError(AppError):
    status_code = 422
    code = "PAYMENT_EVIDENCE_INVALID"
    message = "Payment evidence is invalid"


class PaymentEvidenceTooLargeError(AppError):
    status_code = 413
    code = "PAYMENT_EVIDENCE_TOO_LARGE"
    message = "Payment evidence exceeds the configured size limit"


class PaymentDuplicateError(AppError):
    status_code = 409
    code = "PAYMENT_DUPLICATE"
    message = "Payment evidence or transaction was already used"


class PaymentVerificationProviderError(AppError):
    status_code = 502
    code = "PAYMENT_VERIFICATION_PROVIDER_ERROR"
    message = "Payment verification is temporarily unavailable"


class PaymentVerificationInProgressError(AppError):
    status_code = 409
    code = "PAYMENT_VERIFICATION_IN_PROGRESS"
    message = "Payment verification is already in progress"


class ActionCollectionNotFoundError(AppError):
    status_code = 404
    code = "ACTION_COLLECTION_NOT_FOUND"
    message = "Action collection session not found"


class ActionCollectionStateError(AppError):
    status_code = 409
    code = "ACTION_COLLECTION_STATE_INVALID"
    message = "Action collection session state does not allow this operation"


class ActionCollectionValidationError(AppError):
    status_code = 422
    code = "ACTION_COLLECTION_INPUT_INVALID"
    message = "Action collection input is invalid"


class ActionCollectionConfirmationError(AppError):
    status_code = 401
    code = "ACTION_COLLECTION_CONFIRMATION_INVALID"
    message = "Action confirmation is invalid or expired"


class ActionCollectionProviderError(AppError):
    status_code = 502
    code = "ACTION_COLLECTION_PROVIDER_ERROR"
    message = "Action field extraction is temporarily unavailable"
