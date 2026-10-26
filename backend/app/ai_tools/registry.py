"""Immutable code-defined registry for the constrained OneInFlow AI principal."""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.ai_tools.contracts import (
    AvailabilityResult,
    BookingHoldResult,
    BookingStatusResult,
    CreateBookingHoldInput,
    EmptyToolInput,
    HandoffInput,
    HandoffResult,
    PaymentRequestResult,
    PaymentStatusResult,
    PromotionValidationToolResult,
    RequestBookingPaymentInput,
    RoomCatalogFactsInput,
    SearchAvailabilityInput,
    ValidatePromotionCodeInput,
)
from app.models.ai_tool import AIToolClassification
from app.models.conversation import ConversationMode
from app.schemas.hotel_catalog import CustomerRoomFacts


@dataclass(frozen=True, slots=True)
class AIToolDefinition:
    name: str
    version: str
    description: str
    classification: AIToolClassification
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    extraction_fields: tuple[dict[str, Any], ...]
    handler: str
    confirmation_required: bool
    allowed_modes: frozenset[ConversationMode]
    permission: str

    @property
    def intent_key(self) -> str:
        return f"ai_tool:{self.name}:{self.version}"


class AIToolRegistry:
    def __init__(self, definitions: tuple[AIToolDefinition, ...]) -> None:
        keyed = {(item.name, item.version): item for item in definitions}
        if len(keyed) != len(definitions):
            raise ValueError("AI tool names and versions must be unique")
        self._definitions = keyed

    def list(self) -> tuple[AIToolDefinition, ...]:
        return tuple(self._definitions.values())

    def get(self, name: str, version: str = "1") -> AIToolDefinition:
        try:
            return self._definitions[(name, version)]
        except KeyError as exc:
            raise KeyError(f"Unknown AI tool: {name}@{version}") from exc

    def from_intent_key(self, key: str) -> AIToolDefinition | None:
        if not key.startswith("ai_tool:"):
            return None
        _, name, version = key.split(":", 2)
        return self._definitions.get((name, version))


_MODES = frozenset({ConversationMode.AUTO, ConversationMode.COPILOT})


def _field(key: str, label: str, type_: str, *, required: bool = True):
    return {"key": key, "label": label, "type": type_, "required": required}


def create_ai_tool_registry() -> AIToolRegistry:
    return AIToolRegistry(
        (
            AIToolDefinition(
                "get_room_catalog_facts",
                "1",
                "Read trusted customer-safe room facts such as beds and amenities.",
                AIToolClassification.READ_ONLY,
                RoomCatalogFactsInput,
                CustomerRoomFacts,
                (
                    _field("property_name", "Property", "string", required=False),
                    _field("room_type_name", "Room type", "string"),
                ),
                "get_room_catalog_facts",
                False,
                _MODES,
                "hotel.catalog.read",
            ),
            AIToolDefinition(
                "search_availability",
                "1",
                "Search authoritative room availability and trusted rates.",
                AIToolClassification.READ_ONLY,
                SearchAvailabilityInput,
                AvailabilityResult,
                (
                    _field("property_name", "Property", "string", required=False),
                    _field("check_in", "Check-in date (YYYY-MM-DD)", "string"),
                    _field("check_out", "Check-out date (YYYY-MM-DD)", "string"),
                    _field("adults", "Adults", "integer"),
                    _field("children", "Children", "integer", required=False),
                    _field("room_type_name", "Room type", "string", required=False),
                    _field("rate_plan_name", "Rate plan", "string", required=False),
                ),
                "search_availability",
                False,
                _MODES,
                "hotel.availability.read",
            ),
            AIToolDefinition(
                "quote_availability",
                "1",
                "Quote authoritative room and rate information.",
                AIToolClassification.READ_ONLY,
                SearchAvailabilityInput,
                AvailabilityResult,
                (
                    _field("property_name", "Property", "string", required=False),
                    _field("check_in", "Check-in date (YYYY-MM-DD)", "string"),
                    _field("check_out", "Check-out date (YYYY-MM-DD)", "string"),
                    _field("adults", "Adults", "integer"),
                    _field("children", "Children", "integer", required=False),
                    _field("room_type_name", "Room type", "string", required=False),
                    _field("rate_plan_name", "Rate plan", "string", required=False),
                ),
                "search_availability",
                False,
                _MODES,
                "hotel.availability.read",
            ),
            AIToolDefinition(
                "validate_promotion_code",
                "1",
                "Validate a customer promotion code against a trusted "
                "availability option.",
                AIToolClassification.READ_ONLY,
                ValidatePromotionCodeInput,
                PromotionValidationToolResult,
                (
                    _field("code", "Promotion code", "string"),
                    _field(
                        "option_index",
                        "Selected option number",
                        "integer",
                        required=False,
                    ),
                    _field("quantity", "Rooms", "integer", required=False),
                ),
                "validate_promotion_code",
                False,
                _MODES,
                "hotel.promotion.validate_customer",
            ),
            AIToolDefinition(
                "create_booking_hold",
                "1",
                "Create a temporary booking hold for a previously selected option.",
                AIToolClassification.MUTATING_SENSITIVE,
                CreateBookingHoldInput,
                BookingHoldResult,
                (
                    _field(
                        "option_index",
                        "Selected option number",
                        "integer",
                        required=False,
                    ),
                    _field("check_in", "Check-in date", "string", required=False),
                    _field("check_out", "Check-out date", "string", required=False),
                    _field("adults", "Adults", "integer", required=False),
                    _field("children", "Children", "integer", required=False),
                    _field("quantity", "Rooms", "integer", required=False),
                    _field(
                        "promotion_code",
                        "Promotion code",
                        "string",
                        required=False,
                    ),
                ),
                "create_booking_hold",
                True,
                _MODES,
                "hotel.booking.hold.confirmed_customer",
            ),
            AIToolDefinition(
                "get_booking_status",
                "1",
                "Read the current customer's latest booking state.",
                AIToolClassification.READ_ONLY,
                EmptyToolInput,
                BookingStatusResult,
                (),
                "get_booking_status",
                False,
                _MODES,
                "hotel.booking.read_customer",
            ),
            AIToolDefinition(
                "request_booking_payment",
                "1",
                "Create or return a trusted payment request for a pending booking.",
                AIToolClassification.MUTATING_SENSITIVE,
                RequestBookingPaymentInput,
                PaymentRequestResult,
                (
                    _field(
                        "destination_name",
                        "Payment destination",
                        "string",
                        required=False,
                    ),
                ),
                "request_booking_payment",
                True,
                _MODES,
                "hotel.payment.request_confirmed_customer",
            ),
            AIToolDefinition(
                "get_payment_status",
                "1",
                "Read payment and booking application state for the current customer.",
                AIToolClassification.READ_ONLY,
                EmptyToolInput,
                PaymentStatusResult,
                (),
                "get_payment_status",
                False,
                _MODES,
                "hotel.payment.read_customer",
            ),
            AIToolDefinition(
                "handoff_to_human",
                "1",
                "Hand this conversation to workspace staff.",
                AIToolClassification.MUTATING_REVERSIBLE,
                HandoffInput,
                HandoffResult,
                (_field("reason", "Handoff reason", "string", required=False),),
                "handoff_to_human",
                False,
                _MODES,
                "conversation.handoff",
            ),
        )
    )
