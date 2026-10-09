"""Idempotent public WebChat routing across grounded answers and actions."""

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError, AuthenticationError
from app.integrations.action_extraction import (
    create_action_field_extraction_provider,
)
from app.integrations.action_intent import (
    ActionIntentOption,
    ActionIntentProvider,
    ActionIntentRequest,
    create_action_intent_provider,
)
from app.integrations.embedding import create_embedding_provider
from app.integrations.generation import create_generation_provider
from app.integrations.qdrant_knowledge import QdrantKnowledgeVectorStore
from app.models.action_collection import ActionCollectionStatus
from app.models.ai_tool import AIToolAction, AIToolActionStatus
from app.models.conversation import ConversationMode, HandoffReason
from app.models.message import Message, MessageType, SenderType
from app.repositories.action import ActionDefinitionRepository
from app.repositories.action_collection import ActionCollectionRepository
from app.repositories.message import MessageRepository
from app.schemas.action_collection import ActionCollectionCreate, ActionCollectionInput
from app.schemas.message import MessageCreate
from app.schemas.webchat import WebChatResponseType
from app.services.action_collection import ActionCollectionService
from app.services.ai_tool_orchestration import AIActionOrchestrationService
from app.services.conversation_handoff import ConversationHandoffService
from app.services.grounded_generation import GroundedGenerationService
from app.services.knowledge_retrieval import KnowledgeRetrievalService
from app.services.message import MessageService
from app.services.rag_preparation import RAGPreparationService
from app.services.webchat import WebChatService


class WebChatAIOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        grounded: GroundedGenerationService,
        *,
        intent: ActionIntentProvider | None = None,
        extraction=None,
    ) -> None:
        self.session = session
        self.grounded = grounded
        self.intent = intent or create_action_intent_provider()
        self.webchat = WebChatService(session)
        self.messages = MessageRepository(session)
        self.message_service = MessageService(session)
        self.collections = ActionCollectionRepository(session)
        self.definitions = ActionDefinitionRepository(session)
        extraction_provider = extraction or create_action_field_extraction_provider()
        self.collection_service = ActionCollectionService(session, extraction_provider)
        self.ai_tools = AIActionOrchestrationService(session, extraction_provider)

    async def process(self, conversation_id, token, client_message_id, content):
        stored = await self.webchat.authorize(conversation_id, token)
        conversation = await self.webchat._conversation_or_unauthorized(conversation_id)
        result = await self._process_conversation(
            conversation, client_message_id, content, stored.language
        )
        stored.expires_at = self.webchat._expiry()
        await self.session.commit()
        return result

    async def process_channel(
        self, conversation, external_message_id, content, *, language="en"
    ):
        result = await self._process_conversation(
            conversation, external_message_id, content, language
        )
        await self.session.commit()
        assistant = await self.messages.get_external(
            conversation.id, f"assistant:{external_message_id}"
        )
        return result[0], assistant, result[1]

    async def _process_conversation(
        self, conversation, client_message_id, content, language
    ):
        customer = await self._claim_customer_message(
            conversation, client_message_id, content
        )
        if customer is None:
            return await self._recover(conversation, client_message_id)

        assistant_data: dict[str, Any] | None
        if self._is_explicit_handoff(content):
            await ConversationHandoffService(self.session).request_handoff(
                conversation.workspace_id,
                conversation.id,
                HandoffReason.CUSTOMER_REQUEST,
                deduplication_key=f"channel-handoff:{conversation.id}:{client_message_id}",
                commit=False,
            )
            assistant_data = {
                "type": WebChatResponseType.HUMAN_HANDOFF,
                "message": self._text(language, "handoff"),
                "citations": [],
            }
        elif conversation.ai_mode is ConversationMode.HUMAN:
            assistant_data = None
        else:
            try:
                assistant_data = await self._route(
                    conversation, language, content, client_message_id
                )
            except AppError:
                assistant_data = self._error(language)
            except Exception:
                assistant_data = self._error(language)

        assistant_message = None
        if assistant_data is not None:
            assistant_message = await self._assistant_message(
                conversation.id, client_message_id, assistant_data
            )
        await self.session.flush()
        await self.session.refresh(customer)
        if assistant_message:
            await self.session.refresh(assistant_message)
        return customer, self._public_assistant(assistant_message, assistant_data)

    async def confirm(self, conversation_id, token, session_id, decision):
        stored = await self.webchat.authorize(conversation_id, token)
        conversation = await self.webchat._conversation_or_unauthorized(conversation_id)
        collection = await self._owned_collection(conversation, session_id)
        collection, definition, action = await self.collection_service.confirm(
            conversation.workspace_id,
            None,
            collection.id,
            decision.confirmation_token,
        )
        data = {
            "type": WebChatResponseType.ACTION_CREATED,
            "message": self._text(stored.language, "created"),
            "citations": [],
            "action_request_id": str(action.id),
            "action_collection_session_id": str(collection.id),
        }
        message = await self._action_ack(
            conversation.id, f"confirm:{decision.client_message_id}", data
        )
        return self._public_assistant(message, data)

    async def cancel(self, conversation_id, token, session_id, decision):
        stored = await self.webchat.authorize(conversation_id, token)
        conversation = await self.webchat._conversation_or_unauthorized(conversation_id)
        collection = await self._owned_collection(conversation, session_id)
        await self.collection_service.cancel(conversation.workspace_id, collection.id)
        data = {
            "type": WebChatResponseType.ACTION_CANCELLED,
            "message": self._text(stored.language, "cancelled"),
            "citations": [],
            "action_collection_session_id": str(collection.id),
        }
        message = await self._action_ack(
            conversation.id, f"cancel:{decision.client_message_id}", data
        )
        return self._public_assistant(message, data)

    async def confirm_ai_tool(self, conversation_id, token, action_id, decision):
        stored = await self.webchat.authorize(conversation_id, token)
        conversation = await self.webchat._conversation_or_unauthorized(conversation_id)
        action = await self.ai_tools.confirm(
            conversation.workspace_id,
            conversation.id,
            conversation.customer_id,
            action_id,
            decision.confirmation_token,
        )
        data = self._tool_data(stored.language, action, None)
        message = await self._action_ack(
            conversation.id, f"tool-confirm:{decision.client_message_id}", data
        )
        return self._public_assistant(message, data)

    async def cancel_ai_tool(self, conversation_id, token, action_id, decision):
        stored = await self.webchat.authorize(conversation_id, token)
        conversation = await self.webchat._conversation_or_unauthorized(conversation_id)
        action = await self.ai_tools.cancel(
            conversation.workspace_id,
            conversation.id,
            conversation.customer_id,
            action_id,
        )
        data = self._tool_data(stored.language, action, None)
        message = await self._action_ack(
            conversation.id, f"tool-cancel:{decision.client_message_id}", data
        )
        return self._public_assistant(message, data)

    async def _claim_customer_message(self, conversation, external_id, content):
        try:
            async with self.session.begin_nested():
                return await self.message_service.create_message(
                    conversation.workspace_id,
                    conversation.id,
                    MessageCreate(
                        sender_type=SenderType.CUSTOMER,
                        content=content,
                        external_message_id=external_id,
                    ),
                    commit=False,
                )
        except IntegrityError:
            return None

    async def _recover(self, conversation, client_message_id):
        customer = await self.messages.get_external(conversation.id, client_message_id)
        assistant = await self.messages.get_external(
            conversation.id, f"assistant:{client_message_id}"
        )
        if customer is None:
            raise AuthenticationError("WebChat message retry could not be recovered")
        return customer, await self._recover_assistant(conversation, assistant)

    async def _recover_assistant(self, conversation, assistant):
        if assistant is None:
            return None
        data = dict(assistant.extra_metadata)
        session_id = data.get("action_collection_session_id")
        if (
            data.get("response_type") == WebChatResponseType.ACTION_CONFIRMATION
            and session_id
        ):
            collection = await self.collections.get(
                conversation.workspace_id, uuid.UUID(session_id)
            )
            if collection:
                definition = await self.collection_service._definition(
                    conversation.workspace_id, collection.action_definition_id
                )
                data["confirmation_token"] = self.collection_service.confirmation_token(
                    collection
                )
                data["missing_fields"] = collection.missing_fields
                data["invalid_fields"] = collection.invalid_fields
                data["summary"] = self.collection_service.summary(
                    definition, collection.collected_payload
                )
        tool_action_id = data.get("ai_tool_action_id")
        if tool_action_id:
            action = await self.session.scalar(
                select(AIToolAction).where(
                    AIToolAction.workspace_id == conversation.workspace_id,
                    AIToolAction.conversation_id == conversation.id,
                    AIToolAction.id == uuid.UUID(tool_action_id),
                )
            )
            if action:
                data.update(
                    self._tool_data(
                        "th" if self._contains_thai(assistant.content) else "en",
                        action,
                        self.ai_tools.confirmation_token(action),
                    )
                )
        return self._public_assistant(assistant, data)

    async def _route(self, conversation, language, content, client_message_id):
        normalized = " ".join(content.casefold().split())
        pending_tool = await self.ai_tools.pending_for_conversation(
            conversation.workspace_id, conversation.id
        )
        if pending_tool:
            if normalized in {
                "yes",
                "confirm",
                "confirm request",
                "ยืนยัน",
                "ยืนยันรายการ",
                "ตกลง",
            }:
                pending_tool = await self.ai_tools.confirm(
                    conversation.workspace_id,
                    conversation.id,
                    conversation.customer_id,
                    pending_tool.id,
                    self.ai_tools.confirmation_token(pending_tool),
                )
                return self._tool_data(language, pending_tool, None)
            if normalized in {"no", "cancel", "cancel request", "ยกเลิก", "ไม่เอา"}:
                pending_tool = await self.ai_tools.cancel(
                    conversation.workspace_id,
                    conversation.id,
                    conversation.customer_id,
                    pending_tool.id,
                )
                return self._tool_data(language, pending_tool, None)
            return self._tool_data(
                language,
                pending_tool,
                self.ai_tools.confirmation_token(pending_tool),
            )

        active = await self.collections.get_active_for_conversation(
            conversation.workspace_id, conversation.id
        )
        if active:
            if (
                active.status is ActionCollectionStatus.AWAITING_CONFIRMATION
                and normalized in {"confirm", "confirm request", "ยืนยัน", "ยืนยันรายการ"}
            ):
                token = self.collection_service.confirmation_token(active)
                active, _definition, action = await self.collection_service.confirm(
                    conversation.workspace_id, None, active.id, token
                )
                return {
                    "type": WebChatResponseType.ACTION_CREATED,
                    "message": self._text(language, "created"),
                    "citations": [],
                    "action_request_id": str(action.id),
                    "action_collection_session_id": str(active.id),
                }
            if normalized in {"cancel", "cancel request", "ยกเลิก", "ยกเลิกรายการ"}:
                await self.collection_service.cancel(
                    conversation.workspace_id, active.id
                )
                return {
                    "type": WebChatResponseType.ACTION_CANCELLED,
                    "message": self._text(language, "cancelled"),
                    "citations": [],
                    "action_collection_session_id": str(active.id),
                }
            return await self._continue_collection(
                conversation, language, active, content
            )

        definitions = [
            item
            for item in await self.definitions.list(conversation.workspace_id)
            if item.is_active
        ]
        tools = self.ai_tools.registry.list()
        intent = await self.intent.route(
            ActionIntentRequest(
                message=content,
                options=tuple(
                    ActionIntentOption(item.key, item.name, item.description)
                    for item in definitions
                )
                + tuple(
                    ActionIntentOption(item.intent_key, item.name, item.description)
                    for item in tools
                ),
            )
        )
        tool = (
            self.ai_tools.registry.from_intent_key(intent.selected_action_key)
            if intent.selected_action_key
            else None
        )
        if tool and intent.confidence == 1.0:
            self.ai_tools.require_call_budget(1)
            action, token = await self.ai_tools.propose_from_text(
                conversation,
                tool,
                intent.field_input or content,
                idempotency_key=(
                    f"ai-tool:{conversation.id}:{client_message_id}:"
                    f"{tool.name}:{tool.version}"
                ),
            )
            return self._tool_data(language, action, token)
        definition = next(
            (item for item in definitions if item.key == intent.selected_action_key),
            None,
        )
        if definition and intent.confidence == 1.0:
            fields: dict[str, Any] = {}
            if intent.field_input:
                try:
                    candidate = json.loads(intent.field_input)
                    if isinstance(candidate, dict):
                        fields = candidate
                except json.JSONDecodeError:
                    pass
            (
                collection,
                definition,
                confirmation_token,
            ) = await self.collection_service.create(
                conversation.workspace_id,
                ActionCollectionCreate(
                    action_definition_id=definition.id,
                    conversation_id=conversation.id,
                    customer_id=conversation.customer_id,
                    fields=fields,
                ),
                commit=False,
            )
            return self._collection_data(
                language, collection, definition, confirmation_token
            )
        return await self._grounded(conversation.workspace_id, content)

    async def _continue_collection(self, conversation, language, collection, content):
        definition = await self.collection_service._definition(
            conversation.workspace_id, collection.action_definition_id
        )
        if collection.status is ActionCollectionStatus.AWAITING_CONFIRMATION:
            return self._collection_data(
                language,
                collection,
                definition,
                self.collection_service.confirmation_token(collection),
            )
        if not collection.missing_fields:
            return self._collection_data(language, collection, definition, None)
        key = collection.missing_fields[0]
        (
            collection,
            definition,
            confirmation_token,
        ) = await self.collection_service.add_input(
            conversation.workspace_id,
            collection.id,
            ActionCollectionInput(fields={key: content}),
            commit=False,
        )
        return self._collection_data(
            language, collection, definition, confirmation_token
        )

    async def _grounded(self, workspace_id, content):
        answer = await self.grounded.answer(workspace_id=workspace_id, query=content)
        return {
            "type": WebChatResponseType.ANSWER,
            "message": answer.answer,
            "citations": [
                {
                    "label": item.label,
                    "document_id": str(item.document_id),
                    "chunk_id": str(item.chunk_id),
                    "document_name": item.document_name,
                }
                for item in answer.citations
            ],
            "grounding_status": answer.grounding_status,
        }

    def _collection_data(self, language, collection, definition, token):
        confirmation = collection.status is ActionCollectionStatus.AWAITING_CONFIRMATION
        next_missing = collection.missing_fields[:1]
        label = next(
            (
                item["label"]
                for item in definition.required_fields
                if item["key"] in next_missing
            ),
            None,
        )
        return {
            "type": WebChatResponseType.ACTION_CONFIRMATION
            if confirmation
            else WebChatResponseType.ACTION_COLLECTING,
            "message": self._text(language, "confirm")
            if confirmation
            else self._prompt(language, label),
            "citations": [],
            "action_collection_session_id": str(collection.id),
            "missing_fields": collection.missing_fields,
            "invalid_fields": collection.invalid_fields,
            "summary": self.collection_service.summary(
                definition, collection.collected_payload
            )
            if confirmation
            else None,
            "confirmation_token": token,
        }

    def _tool_data(self, language, action, token):
        if action.status is AIToolActionStatus.AWAITING_CONFIRMATION:
            response_type = WebChatResponseType.AI_TOOL_CONFIRMATION
            message = self._tool_confirmation_message(language, action)
        elif action.status is AIToolActionStatus.CANCELLED:
            response_type = WebChatResponseType.AI_TOOL_CANCELLED
            message = self._text(language, "cancelled")
        elif action.status is AIToolActionStatus.SUCCEEDED:
            response_type = WebChatResponseType.AI_TOOL_RESULT
            message = self._tool_result_message(language, action)
        else:
            response_type = WebChatResponseType.ERROR
            message = self._text(language, "error")
        return {
            "type": response_type,
            "message": message,
            "citations": [],
            "ai_tool_action_id": str(action.id),
            "ai_tool_name": action.tool_name,
            "ai_tool_status": action.status.value,
            "ai_tool_result": action.result,
            "confirmation_token": token,
            "confirmation_expires_at": (
                action.confirmation_expires_at.isoformat()
                if action.confirmation_expires_at
                else None
            ),
        }

    @staticmethod
    def _tool_confirmation_message(language, action):
        thai = (language or "").lower().startswith("th")
        labels = {
            "create_booking_hold": (
                "กรุณายืนยันการสร้างรายการจองชั่วคราว",
                "Please confirm the temporary booking hold.",
            ),
            "request_booking_payment": (
                "กรุณายืนยันการขอช่องทางชำระเงินสำหรับรายการจองนี้",
                "Please confirm the payment request for this booking.",
            ),
        }
        value = labels.get(
            action.tool_name,
            ("กรุณายืนยันรายการนี้", "Please confirm this action."),
        )
        return value[0] if thai else value[1]

    def _tool_result_message(self, language, action):
        thai = (language or "").lower().startswith("th")
        result = action.result or {}
        if action.tool_name in {"search_availability", "quote_availability"}:
            options = result.get("options", [])
            if not options:
                return (
                    "ไม่พบห้องว่างตามวันที่และจำนวนผู้เข้าพักที่ระบุ"
                    if thai
                    else "No rooms are available for the requested stay."
                )
            rendered = "; ".join(
                f"{item['option_index']}. {item['room_type_name']} - "
                f"{item['rate_plan_name']} {item['subtotal']} {item['currency']}"
                for item in options[:3]
            )
            return (
                f"ตัวเลือกที่ว่างจากระบบโรงแรม: {rendered}"
                if thai
                else f"Available options from the hotel system: {rendered}"
            )
        if action.tool_name == "create_booking_hold":
            return (
                "สร้างรายการจองชั่วคราวแล้ว "
                f"ยอดรวม {result.get('total_amount')} {result.get('currency')}"
                if thai
                else "The booking hold was created. "
                f"Total: {result.get('total_amount')} {result.get('currency')}."
            )
        if action.tool_name == "get_booking_status":
            if result.get("payment_requires_review"):
                return (
                    "ได้รับการชำระเงินแล้ว แต่รายการจองยังต้องให้เจ้าหน้าที่ตรวจสอบ"
                    if thai
                    else (
                        "Payment was received, but the booking still requires "
                        "staff review."
                    )
                )
            return (
                f"สถานะรายการจอง: {result.get('booking_status')}"
                if thai
                else f"Booking status: {result.get('booking_status')}."
            )
        if action.tool_name == "request_booking_payment":
            return (
                f"สร้างคำขอชำระเงินแล้ว ยอด {result.get('expected_amount')} "
                f"{result.get('currency')} ผ่าน {result.get('destination_display_name')}"
                if thai
                else f"Payment request created for {result.get('expected_amount')} "
                f"{result.get('currency')} via "
                f"{result.get('destination_display_name')}."
            )
        if action.tool_name == "get_payment_status":
            if result.get("requires_review"):
                return (
                    "ได้รับการชำระเงินแล้ว แต่ต้องให้เจ้าหน้าที่ตรวจสอบก่อนยืนยันการจอง"
                    if thai
                    else (
                        "Payment was received but requires staff review before "
                        "booking confirmation."
                    )
                )
            return (
                f"สถานะการชำระเงิน: {result.get('payment_status')}"
                if thai
                else f"Payment status: {result.get('payment_status')}."
            )
        if action.tool_name == "handoff_to_human":
            return self._text(language, "handoff")
        return self._text(language, "error")

    async def _assistant_message(self, conversation_id, client_id, data):
        metadata = {
            "response_type": str(data["type"]),
            "citations": data.get("citations", []),
            "grounding_status": data.get("grounding_status"),
            "action_collection_session_id": data.get("action_collection_session_id"),
            "action_request_id": data.get("action_request_id"),
            "missing_fields": data.get("missing_fields"),
            "invalid_fields": data.get("invalid_fields"),
            "summary": data.get("summary"),
            "ai_tool_action_id": data.get("ai_tool_action_id"),
            "ai_tool_name": data.get("ai_tool_name"),
            "ai_tool_status": data.get("ai_tool_status"),
            "ai_tool_result": data.get("ai_tool_result"),
            "confirmation_expires_at": data.get("confirmation_expires_at"),
        }
        return await self.message_service.create_message(
            (
                await self.webchat._conversation_or_unauthorized(conversation_id)
            ).workspace_id,
            conversation_id,
            MessageCreate(
                sender_type=SenderType.AI,
                content=data["message"],
                message_type=MessageType.TEXT,
                metadata={
                    key: value for key, value in metadata.items() if value is not None
                },
                external_message_id=f"assistant:{client_id}",
            ),
            commit=False,
        )

    async def _action_ack(self, conversation_id, external_id, data):
        existing = await self.messages.get_external(conversation_id, external_id)
        if existing:
            return existing
        conversation = await self.webchat._conversation_or_unauthorized(conversation_id)
        try:
            async with self.session.begin_nested():
                message = await self.message_service.create_message(
                    conversation.workspace_id,
                    conversation_id,
                    MessageCreate(
                        sender_type=SenderType.AI,
                        content=data["message"],
                        metadata={
                            "response_type": str(data["type"]),
                            "action_collection_session_id": data.get(
                                "action_collection_session_id"
                            ),
                            "action_request_id": data.get("action_request_id"),
                            "ai_tool_action_id": data.get("ai_tool_action_id"),
                            "ai_tool_name": data.get("ai_tool_name"),
                            "ai_tool_status": data.get("ai_tool_status"),
                            "ai_tool_result": data.get("ai_tool_result"),
                        },
                        external_message_id=external_id,
                    ),
                    commit=False,
                )
            await self.session.commit()
            await self.session.refresh(message)
            return message
        except IntegrityError:
            existing = await self.messages.get_external(conversation_id, external_id)
            if existing is None:
                raise
            return existing

    async def _owned_collection(self, conversation, session_id):
        collection = await self.collections.get(
            conversation.workspace_id, session_id, for_update=True
        )
        if (
            collection is None
            or collection.conversation_id != conversation.id
            or collection.customer_id != conversation.customer_id
        ):
            raise AuthenticationError("Invalid WebChat action collection")
        return collection

    def _public_assistant(self, message: Message | None, data):
        if message is None or data is None:
            return {
                "type": WebChatResponseType.HUMAN_MODE,
                "message": None,
                "citations": [],
            }
        response_type = data.get("type") or data.get("response_type")
        return {
            "type": response_type,
            "message": message.content,
            "citations": data.get("citations", []),
            "action_collection": {
                "session_id": data.get("action_collection_session_id"),
                "missing_fields": data.get("missing_fields", []),
                "invalid_fields": data.get("invalid_fields", {}),
                "summary": data.get("summary"),
                "confirmation_token": data.get("confirmation_token"),
            }
            if data.get("action_collection_session_id")
            else None,
            "action_request_id": data.get("action_request_id"),
            "ai_tool_action": {
                "id": data.get("ai_tool_action_id"),
                "tool_name": data.get("ai_tool_name"),
                "status": data.get("ai_tool_status"),
                "result": data.get("ai_tool_result"),
                "confirmation_token": data.get("confirmation_token"),
                "confirmation_expires_at": data.get("confirmation_expires_at"),
            }
            if data.get("ai_tool_action_id")
            else None,
        }

    def _error(self, language):
        return {
            "type": WebChatResponseType.ERROR,
            "message": self._text(language, "error"),
            "citations": [],
        }

    @staticmethod
    def _text(language, key):
        thai = (language or "").lower().startswith("th")
        values = {
            "created": ("ได้รับรายการแล้วค่ะ", "Your request has been received."),
            "cancelled": ("ยกเลิกรายการแล้วค่ะ", "The request has been cancelled."),
            "confirm": (
                "กรุณาตรวจสอบรายละเอียดและกดยืนยัน",
                "Please review and confirm the details.",
            ),
            "error": (
                "ขออภัย ตอนนี้ยังไม่สามารถตอบข้อมูลนี้ได้",
                "Sorry, this request cannot be answered right now.",
            ),
            "handoff": (
                "กำลังส่งต่อให้เจ้าหน้าที่ค่ะ",
                "We are connecting you with a staff member.",
            ),
        }
        return values[key][0 if thai else 1]

    @staticmethod
    def _is_explicit_handoff(content: str) -> bool:
        normalized = " ".join(content.casefold().split())
        phrases = {
            "ขอคุยกับแอดมิน",
            "ขอคุยกับเจ้าหน้าที่",
            "ต้องการคุยกับเจ้าหน้าที่",
            "คุยกับเจ้าหน้าที่",
            "human agent",
            "talk to a human",
            "speak to an agent",
        }
        return normalized in phrases

    @staticmethod
    def _contains_thai(content: str) -> bool:
        return any("\u0e00" <= char <= "\u0e7f" for char in content)

    @staticmethod
    def _prompt(language, label):
        if (language or "").lower().startswith("th"):
            return f"กรุณาระบุ {label or 'ข้อมูลที่จำเป็น'}"
        return f"Please provide {label or 'the required information'}."


def create_webchat_ai_orchestrator(session, qdrant):
    settings = get_settings()
    generation = create_generation_provider(settings)
    retrieval = KnowledgeRetrievalService(
        session,
        settings=settings,
        provider=create_embedding_provider(settings),
        vector_store=QdrantKnowledgeVectorStore(
            qdrant, collection_name=settings.QDRANT_KNOWLEDGE_COLLECTION
        ),
    )
    grounded = GroundedGenerationService(
        RAGPreparationService(retrieval, settings=settings),
        provider=generation,
        settings=settings,
    )
    return WebChatAIOrchestrator(
        session,
        grounded,
        intent=create_action_intent_provider(settings, generation),
        extraction=create_action_field_extraction_provider(settings, generation),
    )
