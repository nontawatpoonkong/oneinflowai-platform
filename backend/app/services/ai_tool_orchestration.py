"""Constrained AI tool policy, confirmation, execution, and safe audit."""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_tools import AIToolDefinition, AIToolRegistry, create_ai_tool_registry
from app.ai_tools.contracts import (
    CreateBookingHoldInput,
    RequestBookingPaymentInput,
    SearchAvailabilityInput,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.integrations.action_extraction import (
    ActionFieldExtractionProvider,
    ActionFieldExtractionRequest,
)
from app.models.ai_tool import (
    AIConversationState,
    AIToolAction,
    AIToolActionStatus,
    AIToolAuditEvent,
    AIToolAuditEventType,
)
from app.models.booking import Booking, BookingStatus
from app.models.conversation import Conversation, ConversationMode, HandoffReason
from app.models.hotel import Property, RatePlan, RoomType
from app.models.payment import Payment, PaymentApplicationStatus, PaymentDestination
from app.schemas.booking import BookingHoldCreate
from app.schemas.hotel import AvailabilitySearchRequest
from app.services.booking import BookingService
from app.services.booking_payment_confirmation import BookingPaymentConfirmationService
from app.services.conversation_handoff import ConversationHandoffService
from app.services.hotel import HotelAvailabilityService


class AIToolError(AppError):
    status_code = 422
    code = "AI_TOOL_INVALID"
    message = "AI tool request is invalid"


class AIToolNotFoundError(AIToolError):
    status_code = 404
    code = "AI_TOOL_NOT_FOUND"
    message = "AI tool action was not found"


class AIToolEligibilityError(AIToolError):
    status_code = 409
    code = "AI_TOOL_NOT_ELIGIBLE"
    message = "AI tool is not eligible in the current context"


class AIToolConfirmationError(AIToolError):
    status_code = 409
    code = "AI_TOOL_CONFIRMATION_INVALID"
    message = "AI tool confirmation is invalid or expired"


class AIToolExecutionError(AIToolError):
    status_code = 409
    code = "AI_TOOL_EXECUTION_FAILED"
    message = "The requested operation could not be completed"


_AI_PERMISSIONS = frozenset(
    {
        "hotel.availability.read",
        "hotel.booking.read_customer",
        "hotel.booking.hold.confirmed_customer",
        "hotel.payment.read_customer",
        "hotel.payment.request_confirmed_customer",
        "conversation.handoff",
    }
)
_MAX_OPTIONS = 10


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(
        _json_value(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


class AIActionOrchestrationService:
    """Executes only code-defined tools under a constrained AI service policy."""

    def __init__(
        self,
        session: AsyncSession,
        extraction: ActionFieldExtractionProvider,
        *,
        registry: AIToolRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.extraction = extraction
        self.registry = registry or create_ai_tool_registry()
        self.settings = settings or get_settings()

    def require_call_budget(self, attempted_calls: int) -> None:
        if attempted_calls > self.settings.AI_TOOL_MAX_CALLS_PER_TURN:
            raise AIToolEligibilityError("AI tool call limit reached for this turn")

    async def propose_from_text(
        self,
        conversation: Conversation,
        tool: AIToolDefinition,
        user_input: str,
        *,
        idempotency_key: str,
    ) -> tuple[AIToolAction, str | None]:
        if tool.permission not in _AI_PERMISSIONS:
            raise AIToolEligibilityError()
        if conversation.ai_mode not in tool.allowed_modes:
            raise AIToolEligibilityError()
        raw: dict[str, Any] = {}
        if tool.extraction_fields:
            extracted = await self.extraction.extract(
                ActionFieldExtractionRequest(
                    field_schema=tool.extraction_fields,
                    user_input=user_input,
                    collected_payload={},
                )
            )
            raw = extracted.candidates
        return await self.propose(
            conversation, tool, raw, idempotency_key=idempotency_key
        )

    async def propose(
        self,
        conversation: Conversation,
        tool: AIToolDefinition,
        raw_args: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[AIToolAction, str | None]:
        await self._validate_conversation(conversation)
        if self.registry.get(tool.name, tool.version) != tool:
            raise AIToolEligibilityError()
        if tool.permission not in _AI_PERMISSIONS:
            raise AIToolEligibilityError()
        if conversation.ai_mode not in tool.allowed_modes:
            raise AIToolEligibilityError()
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"ai-tool:{conversation.workspace_id}:{idempotency_key}"},
        )
        existing = await self.session.scalar(
            select(AIToolAction).where(
                AIToolAction.workspace_id == conversation.workspace_id,
                AIToolAction.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing, self.confirmation_token(existing)
        try:
            parsed = tool.input_model.model_validate(raw_args)
        except ValidationError as exc:
            raise AIToolError(details=self._validation_details(exc)) from exc
        trusted_args = await self._trusted_args(conversation, tool, parsed)
        payload_hash = hashlib.sha256(_canonical(trusted_args).encode()).hexdigest()
        now = datetime.now(UTC)
        action = AIToolAction(
            workspace_id=conversation.workspace_id,
            conversation_id=conversation.id,
            customer_id=conversation.customer_id,
            tool_name=tool.name,
            tool_version=tool.version,
            classification=tool.classification,
            status=(
                AIToolActionStatus.AWAITING_CONFIRMATION
                if tool.confirmation_required
                else AIToolActionStatus.PROPOSED
            ),
            validated_args=_json_value(trusted_args),
            payload_hash=payload_hash,
            confirmation_required=tool.confirmation_required,
            confirmation_expires_at=(
                now + timedelta(minutes=self.settings.AI_TOOL_CONFIRMATION_TTL_MINUTES)
                if tool.confirmation_required
                else None
            ),
            idempotency_key=idempotency_key,
        )
        self.session.add(action)
        await self.session.flush()
        token = self._confirmation_token(action) if tool.confirmation_required else None
        action.confirmation_token_hash = (
            hashlib.sha256(token.encode()).hexdigest() if token else None
        )
        self._audit(action, AIToolAuditEventType.PROPOSED)
        await self.session.commit()
        await self.session.refresh(action)
        if not tool.confirmation_required:
            action = await self._claim_and_execute(
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                action.id,
            )
        return action, token

    async def confirm(
        self,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        customer_id: uuid.UUID,
        action_id: uuid.UUID,
        token: str,
    ) -> AIToolAction:
        action = await self._locked_action(
            workspace_id, conversation_id, customer_id, action_id
        )
        if action.status is AIToolActionStatus.SUCCEEDED:
            self._verify_token(action, token, allow_consumed=True)
            await self.session.commit()
            return action
        if action.status is AIToolActionStatus.EXECUTING:
            raise AIToolConfirmationError("AI tool execution is already in progress")
        if action.status is not AIToolActionStatus.AWAITING_CONFIRMATION:
            raise AIToolConfirmationError()
        if (
            action.confirmation_expires_at is None
            or action.confirmation_expires_at <= datetime.now(UTC)
        ):
            action.status = AIToolActionStatus.EXPIRED
            self._audit(action, AIToolAuditEventType.EXPIRED)
            await self.session.commit()
            raise AIToolConfirmationError()
        self._verify_token(action, token)
        conversation = await self.session.scalar(
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.id == conversation_id,
                Conversation.customer_id == customer_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        tool = self.registry.get(action.tool_name, action.tool_version)
        if conversation is None or conversation.ai_mode not in tool.allowed_modes:
            raise AIToolEligibilityError()
        action.status = AIToolActionStatus.EXECUTING
        action.confirmed_at = datetime.now(UTC)
        self._audit(action, AIToolAuditEventType.CONFIRMED)
        await self.session.commit()
        return await self._execute_claimed(action.id)

    async def cancel(
        self,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        customer_id: uuid.UUID,
        action_id: uuid.UUID,
    ) -> AIToolAction:
        action = await self._locked_action(
            workspace_id, conversation_id, customer_id, action_id
        )
        if action.status is AIToolActionStatus.CANCELLED:
            await self.session.commit()
            return action
        if action.status not in {
            AIToolActionStatus.PROPOSED,
            AIToolActionStatus.AWAITING_CONFIRMATION,
        }:
            raise AIToolConfirmationError("AI tool action can no longer be cancelled")
        action.status = AIToolActionStatus.CANCELLED
        action.cancelled_at = datetime.now(UTC)
        self._audit(action, AIToolAuditEventType.CANCELLED)
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def list_for_conversation(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID, *, limit: int = 50
    ) -> list[AIToolAction]:
        conversation_exists = await self.session.scalar(
            select(Conversation.id).where(
                Conversation.workspace_id == workspace_id,
                Conversation.id == conversation_id,
            )
        )
        if conversation_exists is None:
            raise AIToolNotFoundError()
        return list(
            (
                await self.session.execute(
                    select(AIToolAction)
                    .where(
                        AIToolAction.workspace_id == workspace_id,
                        AIToolAction.conversation_id == conversation_id,
                    )
                    .order_by(AIToolAction.created_at.desc(), AIToolAction.id.desc())
                    .limit(limit)
                )
            ).scalars()
        )

    async def pending_for_conversation(
        self, workspace_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> AIToolAction | None:
        return await self.session.scalar(
            select(AIToolAction)
            .where(
                AIToolAction.workspace_id == workspace_id,
                AIToolAction.conversation_id == conversation_id,
                AIToolAction.status == AIToolActionStatus.AWAITING_CONFIRMATION,
            )
            .order_by(AIToolAction.created_at.desc(), AIToolAction.id.desc())
            .with_for_update()
            .limit(1)
        )

    def confirmation_token(self, action: AIToolAction) -> str | None:
        if action.status is not AIToolActionStatus.AWAITING_CONFIRMATION:
            return None
        return self._confirmation_token(action)

    async def _claim_and_execute(
        self, workspace_id, conversation_id, customer_id, action_id
    ) -> AIToolAction:
        action = await self._locked_action(
            workspace_id, conversation_id, customer_id, action_id
        )
        if action.status is AIToolActionStatus.SUCCEEDED:
            await self.session.commit()
            return action
        if action.status is not AIToolActionStatus.PROPOSED:
            raise AIToolExecutionError()
        action.status = AIToolActionStatus.EXECUTING
        await self.session.commit()
        return await self._execute_claimed(action.id)

    async def _execute_claimed(self, action_id: uuid.UUID) -> AIToolAction:
        action = await self.session.get(AIToolAction, action_id)
        if action is None or action.status is not AIToolActionStatus.EXECUTING:
            raise AIToolExecutionError()
        tool = self.registry.get(action.tool_name, action.tool_version)
        try:
            result, reference = await getattr(self, f"_execute_{tool.handler}")(action)
            validated = tool.output_model.model_validate(result)
            action = await self.session.get(AIToolAction, action_id)
            action.status = AIToolActionStatus.SUCCEEDED
            action.result = _json_value(validated.model_dump())
            action.executed_at = datetime.now(UTC)
            action.error_code = None
            if reference:
                action.result_reference_type, action.result_reference_id = reference
            self._audit(
                action, AIToolAuditEventType.EXECUTED, result_status="SUCCEEDED"
            )
            await self.session.commit()
            await self.session.refresh(action)
            return action
        except AppError as exc:
            await self.session.rollback()
            await self._mark_failed(action_id, exc.code)
            raise AIToolExecutionError(details={"reason": exc.code}) from exc
        except Exception as exc:
            await self.session.rollback()
            await self._mark_failed(action_id, "TOOL_INTERNAL_ERROR")
            raise AIToolExecutionError() from exc

    async def _mark_failed(self, action_id: uuid.UUID, error_code: str) -> None:
        action = await self.session.get(AIToolAction, action_id)
        if action:
            action.status = AIToolActionStatus.FAILED
            action.error_code = error_code
            action.executed_at = datetime.now(UTC)
            self._audit(
                action,
                AIToolAuditEventType.FAILED,
                result_status="FAILED",
                error_code=error_code,
            )
            await self.session.commit()

    async def _trusted_args(self, conversation, tool, parsed):
        if tool.handler == "search_availability":
            return await self._availability_args(conversation, parsed)
        if tool.handler == "create_booking_hold":
            return await self._hold_args(conversation, parsed)
        if tool.handler == "request_booking_payment":
            return await self._payment_args(conversation, parsed)
        if tool.handler in {"get_booking_status", "get_payment_status"}:
            return {
                "conversation_id": conversation.id,
                "customer_id": conversation.customer_id,
            }
        if tool.handler == "handoff_to_human":
            return {"reason": parsed.reason}
        raise AIToolEligibilityError()

    async def _availability_args(
        self, conversation: Conversation, parsed: SearchAvailabilityInput
    ) -> dict[str, Any]:
        prop = await self._resolve_property(
            conversation.workspace_id, parsed.property_name
        )
        room = await self._resolve_room(
            conversation.workspace_id, prop.id, parsed.room_type_name
        )
        plan = await self._resolve_rate(
            conversation.workspace_id,
            prop.id,
            room.id if room else None,
            parsed.rate_plan_name,
        )
        return {
            "property_id": prop.id,
            "check_in": parsed.check_in,
            "check_out": parsed.check_out,
            "adults": parsed.adults,
            "children": parsed.children,
            "room_type_id": room.id if room else None,
            "rate_plan_id": plan.id if plan else None,
        }

    async def _hold_args(
        self, conversation: Conversation, parsed: CreateBookingHoldInput
    ) -> dict[str, Any]:
        state = await self._state(conversation, for_update=True)
        options = state.last_availability_options
        if not options or parsed.option_index > len(options):
            raise AIToolEligibilityError("Search availability before creating a hold")
        option = options[parsed.option_index - 1]
        check_in = parsed.check_in or state.requested_check_in
        check_out = parsed.check_out or state.requested_check_out
        adults = parsed.adults or state.adults
        children = parsed.children if parsed.children is not None else state.children
        if not check_in or not check_out or not adults or children is None:
            raise AIToolEligibilityError("Booking details are incomplete")
        return {
            "property_id": uuid.UUID(option["property_id"]),
            "room_type_id": uuid.UUID(option["room_type_id"]),
            "rate_plan_id": uuid.UUID(option["rate_plan_id"]),
            "check_in": check_in,
            "check_out": check_out,
            "adults": adults,
            "children": children,
            "quantity": parsed.quantity,
            "customer_id": conversation.customer_id,
            "conversation_id": conversation.id,
            "guest_name": None,
        }

    async def _payment_args(
        self, conversation: Conversation, parsed: RequestBookingPaymentInput
    ) -> dict[str, Any]:
        booking = await self._customer_booking(conversation, require_payable=True)
        destinations = list(
            (
                await self.session.execute(
                    select(PaymentDestination)
                    .where(
                        PaymentDestination.workspace_id == conversation.workspace_id,
                        PaymentDestination.is_active.is_(True),
                    )
                    .order_by(
                        PaymentDestination.is_default.desc(),
                        PaymentDestination.created_at,
                    )
                )
            ).scalars()
        )
        if parsed.destination_name:
            normalized = parsed.destination_name.casefold().strip()
            destinations = [
                item
                for item in destinations
                if item.display_name.casefold() == normalized
            ]
        if not destinations:
            raise AIToolEligibilityError("No active payment destination is available")
        if (
            not parsed.destination_name
            and len(destinations) > 1
            and not destinations[0].is_default
        ):
            raise AIToolEligibilityError("Payment destination is ambiguous")
        destination = destinations[0]
        return {"booking_id": booking.id, "destination_id": destination.id}

    async def _execute_search_availability(self, action):
        request = AvailabilitySearchRequest.model_validate(action.validated_args)
        response = await HotelAvailabilityService(self.session).search(
            action.workspace_id, request
        )
        prop = await self.session.get(Property, request.property_id)
        options = []
        state_options = []
        for index, item in enumerate(response.results[:_MAX_OPTIONS], start=1):
            options.append(
                {
                    "option_index": index,
                    "property_name": prop.name,
                    "room_type_name": item.room_type_name,
                    "rate_plan_name": item.rate_plan_name,
                    "check_in": response.check_in,
                    "check_out": response.check_out,
                    "currency": item.currency,
                    "subtotal": item.subtotal,
                    "available_units": item.available_units,
                    "refundable": item.refundable,
                }
            )
            state_options.append(
                {
                    "property_id": str(item.property_id),
                    "room_type_id": str(item.room_type_id),
                    "rate_plan_id": str(item.rate_plan_id),
                }
            )
        state = await self._state_for_ids(
            action.workspace_id, action.conversation_id, for_update=True
        )
        state.selected_property_id = request.property_id
        state.selected_room_type_id = (
            response.results[0].room_type_id if response.results else None
        )
        state.selected_rate_plan_id = (
            response.results[0].rate_plan_id if response.results else None
        )
        state.requested_check_in = request.check_in
        state.requested_check_out = request.check_out
        state.adults = request.adults
        state.children = request.children
        state.quantity = 1
        state.last_availability_options = state_options
        await self.session.flush()
        return {"options": options}, None

    async def _execute_create_booking_hold(self, action):
        request = BookingHoldCreate.model_validate(
            {
                **action.validated_args,
                "idempotency_key": f"ai-tool:{action.id}",
            }
        )
        booking = await BookingService(self.session).create_hold(
            action.workspace_id, None, request, source="AI"
        )
        detail = await BookingService(self.session).detail(
            action.workspace_id, booking.id
        )
        state = await self._state_for_ids(
            action.workspace_id, action.conversation_id, for_update=True
        )
        state.active_booking_id = booking.id
        await self.session.flush()
        return self._booking_result(detail), ("booking", booking.id)

    async def _execute_get_booking_status(self, action):
        conversation = await self.session.get(Conversation, action.conversation_id)
        booking = await self._customer_booking(conversation)
        detail = await BookingService(self.session).detail(
            action.workspace_id, booking.id
        )
        payment = await self._latest_payment(action.workspace_id, booking.id)
        result = self._booking_result(detail)
        result.update(
            {
                "payment_status": payment.status.value if payment else None,
                "payment_application_status": (
                    payment.booking_application_status.value
                    if payment and payment.booking_application_status
                    else None
                ),
                "payment_requires_review": bool(
                    payment
                    and payment.booking_application_status
                    is PaymentApplicationStatus.REQUIRES_REVIEW
                ),
            }
        )
        return result, ("booking", booking.id)

    async def _execute_request_booking_payment(self, action):
        args = action.validated_args
        payment = await BookingPaymentConfirmationService(
            self.session
        ).initiate_payment(
            action.workspace_id,
            uuid.UUID(args["booking_id"]),
            uuid.UUID(args["destination_id"]),
            None,
        )
        destination = await self.session.get(
            PaymentDestination, payment.payment_destination_id
        )
        booking = await self.session.get(Booking, payment.booking_id)
        return {
            "payment_status": payment.status.value,
            "booking_status": booking.status.value,
            "currency": payment.currency,
            "expected_amount": payment.expected_amount,
            "destination_display_name": destination.display_name,
            "destination_type": destination.type.value,
            "destination_account_masked": destination.account_number_masked,
            "destination_promptpay_last4": destination.promptpay_identifier_last4,
            "expires_at": payment.expires_at,
        }, ("payment", payment.id)

    async def _execute_get_payment_status(self, action):
        conversation = await self.session.get(Conversation, action.conversation_id)
        booking = await self._customer_booking(conversation)
        payment = await self._latest_payment(action.workspace_id, booking.id)
        if payment is None:
            raise NotFoundError("Payment not found")
        requires_review = (
            payment.booking_application_status
            is PaymentApplicationStatus.REQUIRES_REVIEW
        )
        return {
            "payment_status": payment.status.value,
            "booking_status": booking.status.value,
            "application_status": (
                payment.booking_application_status.value
                if payment.booking_application_status
                else None
            ),
            "requires_review": requires_review,
            "review_reason": (
                payment.booking_application_reason.value
                if payment.booking_application_reason
                else None
            ),
            "currency": payment.currency,
            "expected_amount": payment.expected_amount,
            "verified_amount": payment.verified_amount,
        }, ("payment", payment.id)

    async def _execute_handoff_to_human(self, action):
        await ConversationHandoffService(self.session).request_handoff(
            action.workspace_id,
            action.conversation_id,
            HandoffReason.CUSTOMER_REQUEST,
            deduplication_key=f"ai-tool-handoff:{action.id}",
            commit=False,
        )
        return {
            "conversation_mode": ConversationMode.HUMAN.value,
            "handoff_reason": HandoffReason.CUSTOMER_REQUEST.value,
        }, ("conversation", action.conversation_id)

    async def _resolve_property(self, workspace_id, name):
        statement = select(Property).where(
            Property.workspace_id == workspace_id, Property.active.is_(True)
        )
        if name:
            statement = statement.where(Property.name.ilike(name.strip()))
        values = list(
            (await self.session.execute(statement.order_by(Property.id))).scalars()
        )
        if len(values) != 1:
            raise AIToolEligibilityError("Property is missing or ambiguous")
        return values[0]

    async def _resolve_room(self, workspace_id, property_id, name):
        if not name:
            return None
        normalized = name.strip()
        values = list(
            (
                await self.session.execute(
                    select(RoomType).where(
                        RoomType.workspace_id == workspace_id,
                        RoomType.property_id == property_id,
                        RoomType.active.is_(True),
                        or_(
                            RoomType.name.ilike(normalized),
                            RoomType.code.ilike(normalized),
                        ),
                    )
                )
            ).scalars()
        )
        if len(values) != 1:
            raise AIToolEligibilityError("Room type is unknown or ambiguous")
        return values[0]

    async def _resolve_rate(self, workspace_id, property_id, room_id, name):
        if not name:
            return None
        normalized = name.strip()
        statement = select(RatePlan).where(
            RatePlan.workspace_id == workspace_id,
            RatePlan.property_id == property_id,
            RatePlan.active.is_(True),
            or_(RatePlan.name.ilike(normalized), RatePlan.code.ilike(normalized)),
        )
        if room_id:
            statement = statement.where(RatePlan.room_type_id == room_id)
        values = list((await self.session.execute(statement)).scalars())
        if len(values) != 1:
            raise AIToolEligibilityError("Rate plan is unknown or ambiguous")
        return values[0]

    async def _customer_booking(self, conversation, *, require_payable=False):
        statement = (
            select(Booking)
            .where(
                Booking.workspace_id == conversation.workspace_id,
                Booking.customer_id == conversation.customer_id,
                or_(
                    Booking.conversation_id == conversation.id,
                    Booking.conversation_id.is_(None),
                ),
            )
            .order_by(Booking.created_at.desc(), Booking.id.desc())
        )
        if require_payable:
            statement = statement.where(Booking.status == BookingStatus.PENDING_PAYMENT)
        booking = await self.session.scalar(statement.limit(1))
        if booking is None:
            raise AIToolEligibilityError("No eligible customer booking was found")
        return booking

    async def _latest_payment(self, workspace_id, booking_id):
        return await self.session.scalar(
            select(Payment)
            .where(
                Payment.workspace_id == workspace_id,
                Payment.booking_id == booking_id,
            )
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(1)
        )

    @staticmethod
    def _booking_result(detail):
        booking_item = detail["item"]
        return {
            "booking_status": detail["status"].value,
            "property_name": detail["property_name_snapshot"],
            "room_type_name": booking_item.room_type_name_snapshot,
            "rate_plan_name": booking_item.rate_plan_name_snapshot,
            "check_in": detail["check_in"],
            "check_out": detail["check_out"],
            "currency": detail["currency"],
            "total_amount": detail["total_amount"],
            "hold_expires_at": detail["hold_expires_at"],
        }

    async def _state(self, conversation, *, for_update=False):
        return await self._state_for_ids(
            conversation.workspace_id,
            conversation.id,
            for_update=for_update,
        )

    async def _state_for_ids(self, workspace_id, conversation_id, *, for_update=False):
        statement = select(AIConversationState).where(
            AIConversationState.workspace_id == workspace_id,
            AIConversationState.conversation_id == conversation_id,
        )
        if for_update:
            statement = statement.with_for_update()
        state = await self.session.scalar(statement)
        if state is None:
            state = AIConversationState(
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                last_availability_options=[],
            )
            self.session.add(state)
            await self.session.flush()
        return state

    async def _locked_action(
        self, workspace_id, conversation_id, customer_id, action_id
    ):
        action = await self.session.scalar(
            select(AIToolAction)
            .where(
                AIToolAction.workspace_id == workspace_id,
                AIToolAction.conversation_id == conversation_id,
                AIToolAction.customer_id == customer_id,
                AIToolAction.id == action_id,
            )
            .with_for_update()
        )
        if action is None:
            raise AIToolNotFoundError()
        return action

    async def _validate_conversation(self, conversation):
        trusted = await self.session.scalar(
            select(Conversation).where(
                Conversation.workspace_id == conversation.workspace_id,
                Conversation.id == conversation.id,
                Conversation.customer_id == conversation.customer_id,
            )
        )
        if trusted is None:
            raise AIToolEligibilityError()

    def _verify_token(self, action, token, *, allow_consumed=False):
        expected = action.confirmation_token_hash
        actual = hashlib.sha256(token.encode()).hexdigest()
        if not expected or not hmac.compare_digest(expected, actual):
            raise AIToolConfirmationError()
        if (
            action.payload_hash
            != hashlib.sha256(_canonical(action.validated_args).encode()).hexdigest()
        ):
            raise AIToolConfirmationError()
        if not allow_consumed and action.confirmation_expires_at is None:
            raise AIToolConfirmationError()

    @staticmethod
    def _confirmation_token(action):
        return hmac.new(
            action.idempotency_key.encode(),
            f"{action.id}:{action.payload_hash}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def _audit(
        self,
        action,
        event_type,
        *,
        result_status=None,
        error_code=None,
    ):
        self.session.add(
            AIToolAuditEvent(
                workspace_id=action.workspace_id,
                action_id=action.id,
                conversation_id=action.conversation_id,
                customer_id=action.customer_id,
                event_type=event_type,
                tool_name=action.tool_name,
                tool_version=action.tool_version,
                result_status=result_status,
                error_code=error_code,
                event_metadata={"classification": action.classification.value},
            )
        )

    @staticmethod
    def _validation_details(exc: ValidationError):
        return {
            "fields": sorted(
                {str(error["loc"][0]) for error in exc.errors() if error.get("loc")}
            )
        }
