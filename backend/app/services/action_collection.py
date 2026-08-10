"""Safe multi-turn action field collection and explicit confirmation."""

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ActionCollectionConfirmationError,
    ActionCollectionNotFoundError,
    ActionCollectionProviderError,
    ActionCollectionStateError,
    ActionCollectionValidationError,
    ActionNotFoundError,
    ActionPayloadValidationError,
)
from app.integrations.action_extraction import (
    ActionFieldExtractionProvider,
    ActionFieldExtractionRequest,
)
from app.models.action import ActionActorType, ActionDefinition, ActionPriority
from app.models.action_collection import (
    ActionCollectionSession,
    ActionCollectionStatus,
)
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.repositories.action import ActionDefinitionRepository, ActionRequestRepository
from app.repositories.action_collection import ActionCollectionRepository
from app.schemas.action import ActionCreate
from app.services.action import ActionService
from app.services.action_validation import ActionPayloadValidator


class ActionCollectionService:
    def __init__(
        self,
        session: AsyncSession,
        provider: ActionFieldExtractionProvider,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.settings = settings or get_settings()
        self.collections = ActionCollectionRepository(session)
        self.definitions = ActionDefinitionRepository(session)
        self.actions = ActionRequestRepository(session)
        self.validator = ActionPayloadValidator()

    async def create(self, workspace_id, data, *, commit: bool = True):
        definition = await self._definition(workspace_id, data.action_definition_id)
        await self._validate_links(workspace_id, data.conversation_id, data.customer_id)
        now = datetime.now(UTC)
        collection = ActionCollectionSession(
            workspace_id=workspace_id,
            action_definition_id=definition.id,
            conversation_id=data.conversation_id,
            customer_id=data.customer_id,
            status=ActionCollectionStatus.COLLECTING,
            collected_payload={},
            missing_fields=[field["key"] for field in definition.required_fields],
            invalid_fields={},
            action_idempotency_key=f"action-collection:{secrets.token_urlsafe(32)}",
            created_by_type=ActionActorType.HUMAN,
            expires_at=now
            + timedelta(minutes=self.settings.ACTION_COLLECTION_SESSION_TTL_MINUTES),
        )
        await self.collections.add(collection)
        candidates = dict(data.fields)
        if data.initial_input:
            candidates.update(
                await self._extract(definition, data.initial_input, collection)
            )
        token = await self._apply(definition, collection, candidates)
        if commit:
            await self.session.commit()
            await self.session.refresh(collection)
        return collection, definition, token

    async def add_input(self, workspace_id, session_id, data, *, commit: bool = True):
        collection = await self._get_active(workspace_id, session_id, for_update=True)
        if collection.status in {
            ActionCollectionStatus.CONFIRMED,
            ActionCollectionStatus.CANCELLED,
        }:
            raise ActionCollectionStateError()
        definition = await self._definition(
            workspace_id, collection.action_definition_id
        )
        candidates = dict(data.fields)
        if data.input:
            candidates.update(await self._extract(definition, data.input, collection))
        token = await self._apply(definition, collection, candidates)
        if commit:
            await self.session.commit()
            await self.session.refresh(collection)
        return collection, definition, token

    async def get(self, workspace_id, session_id):
        collection = await self._get_active(workspace_id, session_id)
        definition = await self._definition(
            workspace_id, collection.action_definition_id
        )
        return collection, definition

    async def cancel(self, workspace_id, session_id):
        collection = await self._get_active(workspace_id, session_id, for_update=True)
        if collection.status is ActionCollectionStatus.CONFIRMED:
            raise ActionCollectionStateError()
        if collection.status is not ActionCollectionStatus.CANCELLED:
            collection.status = ActionCollectionStatus.CANCELLED
            collection.cancelled_at = datetime.now(UTC)
            collection.confirmation_token_hash = None
            collection.confirmation_expires_at = None
            await self.session.commit()
            await self.session.refresh(collection)
        definition = await self._definition(
            workspace_id, collection.action_definition_id
        )
        return collection, definition

    async def confirm(self, workspace_id, user_id, session_id, token):
        collection = await self.collections.get(
            workspace_id, session_id, for_update=True
        )
        if not collection:
            raise ActionCollectionNotFoundError()
        definition = await self._definition(
            workspace_id, collection.action_definition_id
        )
        if collection.status is ActionCollectionStatus.CONFIRMED:
            self._verify_token(collection, token, allow_consumed=True)
            action = await self.actions.get(workspace_id, collection.action_request_id)
            return collection, definition, action
        await self._expire_if_needed(collection)
        if collection.status is not ActionCollectionStatus.AWAITING_CONFIRMATION:
            raise ActionCollectionStateError()
        self._verify_token(collection, token)
        payload = self.validator.validate(definition, collection.collected_payload)
        action = await ActionService(self.session).create(
            workspace_id,
            user_id,
            ActionCreate(
                action_definition_id=definition.id,
                conversation_id=collection.conversation_id,
                customer_id=collection.customer_id,
                priority=ActionPriority.NORMAL,
                payload=payload,
                idempotency_key=collection.action_idempotency_key,
            ),
            commit=False,
        )
        collection.status = ActionCollectionStatus.CONFIRMED
        collection.action_request_id = action.id
        collection.confirmed_at = datetime.now(UTC)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(collection)
        await self.session.refresh(action)
        return collection, definition, action

    async def _apply(self, definition, collection, candidates):
        combined = {**collection.collected_payload, **candidates}
        try:
            normalized, missing, invalid = self.validator.validate_partial(
                definition, combined
            )
        except ActionPayloadValidationError as exc:
            raise ActionCollectionValidationError(details=exc.details) from exc
        collection.collected_payload = normalized
        collection.missing_fields = missing
        collection.invalid_fields = invalid
        collection.confirmation_token_hash = None
        collection.confirmation_expires_at = None
        if missing or invalid:
            collection.status = ActionCollectionStatus.COLLECTING
            return None
        token = self._confirmation_token(collection, normalized)
        collection.status = ActionCollectionStatus.AWAITING_CONFIRMATION
        collection.confirmation_expires_at = min(
            collection.expires_at, datetime.now(UTC) + timedelta(minutes=10)
        )
        collection.confirmation_token_hash = self._token_hash(token, normalized)
        return token

    async def _extract(self, definition, user_input, collection):
        fields = (*definition.required_fields, *definition.optional_fields)
        try:
            result = await self.provider.extract(
                ActionFieldExtractionRequest(
                    field_schema=fields,
                    user_input=user_input,
                    collected_payload=dict(collection.collected_payload),
                )
            )
        except ActionCollectionProviderError:
            raise
        except Exception as exc:
            raise ActionCollectionProviderError() from exc
        if not isinstance(result.candidates, dict):
            raise ActionCollectionProviderError()
        return result.candidates

    async def _definition(self, workspace_id, definition_id):
        definition = await self.definitions.get(workspace_id, definition_id)
        if not definition or not definition.is_active:
            raise ActionNotFoundError("Active action definition not found")
        return definition

    async def _validate_links(self, workspace_id, conversation_id, customer_id):
        if conversation_id:
            conversation = await self.session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.workspace_id == workspace_id,
                )
            )
            if not conversation:
                raise ActionNotFoundError("Conversation not found")
            if customer_id and conversation.customer_id != customer_id:
                raise ActionCollectionValidationError(
                    "Conversation and customer do not match"
                )
        if customer_id and not await self.session.scalar(
            select(Customer.id).where(
                Customer.id == customer_id,
                Customer.workspace_id == workspace_id,
                Customer.deleted_at.is_(None),
            )
        ):
            raise ActionNotFoundError("Customer not found")

    async def _get_active(self, workspace_id, session_id, *, for_update=False):
        collection = await self.collections.get(
            workspace_id, session_id, for_update=for_update
        )
        if not collection:
            raise ActionCollectionNotFoundError()
        await self._expire_if_needed(collection)
        return collection

    async def _expire_if_needed(self, collection):
        if collection.status not in {
            ActionCollectionStatus.CONFIRMED,
            ActionCollectionStatus.CANCELLED,
        } and collection.expires_at <= datetime.now(UTC):
            collection.status = ActionCollectionStatus.EXPIRED
            collection.confirmation_token_hash = None
            collection.confirmation_expires_at = None
            await self.session.commit()
            raise ActionCollectionStateError("Action collection session has expired")
        if collection.status is ActionCollectionStatus.EXPIRED:
            raise ActionCollectionStateError("Action collection session has expired")

    def _verify_token(self, collection, token, *, allow_consumed=False):
        if not allow_consumed and (
            not collection.confirmation_expires_at
            or collection.confirmation_expires_at <= datetime.now(UTC)
        ):
            raise ActionCollectionConfirmationError()
        expected = collection.confirmation_token_hash
        actual = self._token_hash(token, collection.collected_payload)
        if not expected or not hmac.compare_digest(expected, actual):
            raise ActionCollectionConfirmationError()

    def confirmation_token(self, collection) -> str | None:
        if collection.status is not ActionCollectionStatus.AWAITING_CONFIRMATION:
            return None
        return self._confirmation_token(collection, collection.collected_payload)

    @staticmethod
    def _token_hash(token: str, payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(f"{token}:{canonical}".encode()).hexdigest()

    @staticmethod
    def _confirmation_token(collection, payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hmac.new(
            collection.action_idempotency_key.encode(),
            f"{collection.id}:{canonical}".encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def summary(definition: ActionDefinition, payload: dict[str, Any]):
        fields = [*definition.required_fields, *definition.optional_fields]
        return {
            "action": definition.name,
            "fields": [
                {
                    "key": field["key"],
                    "label": field["label"],
                    "value": payload[field["key"]],
                }
                for field in fields
                if field["key"] in payload
            ],
        }

    @staticmethod
    def missing_metadata(definition, missing):
        wanted = set(missing)
        return [
            {key: field[key] for key in ("key", "label", "type")}
            for field in definition.required_fields
            if field["key"] in wanted
        ]
