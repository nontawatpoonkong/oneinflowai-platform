"""Which workspace capabilities a staff caller needs to read an AI tool result.

Tool results are typed per tool, and each result type belongs to a domain with
its own capability, independent of the conversation.read that lists the tool
actions. A result type missing from this map is never shown (fail closed).
"""

from pydantic import BaseModel

from app.ai_tools.contracts import (
    AvailabilityResult,
    BookingHoldResult,
    BookingStatusResult,
    HandoffResult,
    PaymentRequestResult,
    PaymentStatusResult,
    PromotionValidationToolResult,
)
from app.ai_tools.registry import AIToolRegistry
from app.schemas.hotel_catalog import CustomerRoomFacts
from app.services.workspace_capability import WorkspaceCapability

_ROOM = WorkspaceCapability.ROOM_READ
_BOOKING = WorkspaceCapability.BOOKING_READ
_PAYMENT = WorkspaceCapability.PAYMENT_READ

RESULT_CAPABILITIES: dict[type[BaseModel], frozenset[WorkspaceCapability]] = {
    CustomerRoomFacts: frozenset({_ROOM}),
    AvailabilityResult: frozenset({_ROOM}),
    PromotionValidationToolResult: frozenset(
        {_ROOM, WorkspaceCapability.PROMOTION_READ}
    ),
    BookingHoldResult: frozenset({_BOOKING}),
    # Booking status carries payment state; payment results carry booking state.
    BookingStatusResult: frozenset({_BOOKING, _PAYMENT}),
    PaymentRequestResult: frozenset({_BOOKING, _PAYMENT}),
    PaymentStatusResult: frozenset({_BOOKING, _PAYMENT}),
    HandoffResult: frozenset(),
}


def visible_message_metadata(
    metadata: dict,
    tools: dict[str, tuple[str, str]],
    registry: AIToolRegistry,
    capabilities: frozenset[WorkspaceCapability],
) -> dict:
    """Withhold a stored ``ai_tool_result`` the caller may not read.

    ``tools`` maps AI tool action ids of the same Workspace and conversation
    to their tool name and version; the tool is taken from that row, never
    from the message metadata. Unknown or foreign ids stay hidden.
    """

    if metadata.get("ai_tool_result") is None:
        return metadata
    tool = tools.get(str(metadata.get("ai_tool_action_id")))
    if tool is not None and result_visible(registry, *tool, capabilities):
        return metadata
    return {**metadata, "ai_tool_result": None, "ai_tool_result_visible": False}


def result_visible(
    registry: AIToolRegistry,
    tool_name: str,
    tool_version: str,
    capabilities: frozenset[WorkspaceCapability],
) -> bool:
    try:
        output_model = registry.get(tool_name, tool_version).output_model
    except KeyError:
        return False
    required = RESULT_CAPABILITIES.get(output_model)
    return required is not None and required <= capabilities
