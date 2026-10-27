"""PostgreSQL-backed safe AI action orchestration regressions."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, update

from app.ai_tools import AIToolRegistry, create_ai_tool_registry
from app.core.config import Settings
from app.integrations.action_extraction import ActionFieldExtractionResult
from app.models.ai_tool import (
    AIConversationState,
    AIToolAction,
    AIToolActionStatus,
    AIToolAuditEvent,
    AIToolAuditEventType,
    AIToolClassification,
)
from app.models.automation import DomainEventOutbox
from app.models.booking import Booking, BookingStatus
from app.models.conversation import Conversation, ConversationMode
from app.models.hotel import InventoryDate
from app.models.hotel_catalog import RoomTypeAmenity
from app.models.payment import (
    DestinationType,
    Payment,
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentDestination,
    PaymentStatus,
)
from app.services.ai_tool_orchestration import (
    AIActionOrchestrationService,
    AIToolConfirmationError,
    AIToolEligibilityError,
    AIToolError,
    AIToolExecutionError,
    AIToolNotFoundError,
)
from app.services.booking import BookingService
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_hotel import _auth, _inventory, _property, _rate, _room
from tests.test_promotions import _promotion


class FakeExtraction:
    async def extract(self, request):
        return ActionFieldExtractionResult("test", {})


def _setup(client, email="ai-tools@example.com"):
    client.headers["host"] = "localhost"
    user, token = register_verify_and_login(client, email=email)
    headers = _auth(token)
    assert client.post("/api/v1/channels/webchat", headers=headers).status_code == 200
    webchat = client.post(
        "/api/v1/webchat/sessions",
        json={"workspace_key": user["workspace"]["slug"], "name": "Guest"},
    )
    assert webchat.status_code == 201, webchat.text
    prop = _property(client, token)
    room = _room(client, token, prop["id"])
    rate = _rate(client, token, prop["id"], room["id"])
    inventory = _inventory(
        client,
        token,
        prop["id"],
        room["id"],
        total_units=2,
        reserved_units=0,
        blocked_units=0,
    )
    assert inventory.status_code == 200, inventory.text
    return {
        "workspace_id": uuid.UUID(user["workspace"]["id"]),
        "token": token,
        "headers": headers,
        "webchat": webchat.json()["data"],
        "property": prop,
        "room": room,
        "rate": rate,
    }


async def _conversation(setup):
    async with TestSessionLocal() as session:
        value = await session.get(
            Conversation, uuid.UUID(setup["webchat"]["conversation_id"])
        )
        assert value is not None
        return value


def _search_args(setup):
    return {
        "property_name": setup["property"]["name"],
        "check_in": "2030-01-01",
        "check_out": "2030-01-04",
        "adults": 2,
        "children": 0,
    }


async def _search(session, conversation, setup, *, key="search-1"):
    service = AIActionOrchestrationService(session, FakeExtraction())
    return await service.propose(
        conversation,
        service.registry.get("search_availability"),
        _search_args(setup),
        idempotency_key=key,
    )


def test_registry_is_code_defined_versioned_and_excludes_forbidden_tools():
    registry = create_ai_tool_registry()
    names = {item.name for item in registry.list()}
    assert {
        "search_availability",
        "quote_availability",
        "get_room_catalog_facts",
        "validate_promotion_code",
        "create_booking_hold",
        "get_booking_status",
        "request_booking_payment",
        "get_payment_status",
        "handoff_to_human",
    } == names
    assert {item.version for item in registry.list()} == {"1"}
    assert not {
        "confirm_booking",
        "verify_payment",
        "check_in",
        "check_out",
        "housekeeping_complete",
        "readiness_override",
    }.intersection(names)
    with pytest.raises(KeyError):
        registry.get("arbitrary_python")
    with pytest.raises(ValueError):
        AIToolRegistry((registry.get("search_availability"),) * 2)


@pytest.mark.parametrize(
    "overrides",
    [
        {"AI_TOOL_MAX_CALLS_PER_TURN": 0},
        {"AI_TOOL_MAX_CALLS_PER_TURN": 4},
        {"AI_TOOL_CONFIRMATION_TTL_MINUTES": 0},
        {"AI_TOOL_CONFIRMATION_TTL_MINUTES": 61},
    ],
)
def test_ai_tool_settings_reject_unbounded_values(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_tool_call_budget_is_bounded():
    service = AIActionOrchestrationService(
        None,
        FakeExtraction(),
        settings=Settings(_env_file=None, AI_TOOL_MAX_CALLS_PER_TURN=3),
    )
    service.require_call_budget(3)
    with pytest.raises(AIToolEligibilityError):
        service.require_call_budget(4)


def test_read_only_availability_uses_authoritative_service_and_bounded_state(client_db):
    setup = _setup(client_db)

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            action, token = await _search(session, conversation, setup)
            service = AIActionOrchestrationService(session, FakeExtraction())
            state = await session.scalar(
                select(AIConversationState).where(
                    AIConversationState.workspace_id == setup["workspace_id"],
                    AIConversationState.conversation_id == conversation.id,
                )
            )
            audits = list(
                (
                    await session.execute(
                        select(AIToolAuditEvent).where(
                            AIToolAuditEvent.action_id == action.id
                        )
                    )
                ).scalars()
            )
            assert token is None
            assert action.status is AIToolActionStatus.SUCCEEDED
            assert action.result["options"][0]["subtotal"] == "4500.75"
            assert action.result["options"][0]["available_units"] == 2
            assert len(state.last_availability_options) == 1
            assert state.selected_property_id == uuid.UUID(setup["property"]["id"])
            assert [item.event_type for item in audits] == [
                AIToolAuditEventType.PROPOSED,
                AIToolAuditEventType.EXECUTED,
            ]
            assert all(
                set(item.event_metadata) == {"classification"} for item in audits
            )
            quote, quote_token = await service.propose(
                conversation,
                service.registry.get("quote_availability"),
                _search_args(setup),
                idempotency_key="quote-1",
            )
            assert quote_token is None
            assert quote.status is AIToolActionStatus.SUCCEEDED
            assert quote.result["options"][0]["subtotal"] == "4500.75"

    asyncio.run(run())


def test_promotion_validation_tool_and_hold_use_authoritative_pricing(client_db):
    setup = _setup(client_db, "ai-promotion@example.com")
    _promotion(
        client_db,
        setup["token"],
        setup["property"],
        setup["room"],
        setup["rate"],
        sources=["WEBCHAT"],
    )

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            await _search(session, conversation, setup, key="promotion-search")
            service = AIActionOrchestrationService(session, FakeExtraction())
            validation, token = await service.propose(
                conversation,
                service.registry.get("validate_promotion_code"),
                {"code": "welcome10", "option_index": 1},
                idempotency_key="promotion-validation",
            )
            assert token is None
            assert validation.status is AIToolActionStatus.SUCCEEDED
            assert validation.result == {
                "valid": True,
                "reason_code": None,
                "code": "WELCOME10",
                "promotion_name": "Rule WELCOME10",
                "discount_amount": "450.08",
                "subtotal": "4500.75",
                "final_total": "4050.67",
                "currency": "THB",
            }
            hold, confirmation = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1, "promotion_code": "WELCOME10"},
                idempotency_key="promotion-hold",
            )
            assert confirmation
            executed = await service.confirm(
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                hold.id,
                confirmation,
            )
            assert executed.result["subtotal"] == "4500.75"
            assert executed.result["discount_amount"] == "450.08"
            assert executed.result["total_amount"] == "4050.67"
            assert executed.result["promotion_code"] == "WELCOME10"

    asyncio.run(run())


def test_room_catalog_tool_reads_structured_facts_without_mutation(client_db):
    setup = _setup(client_db, "ai-catalog@example.com")
    response = client_db.put(
        f"/api/v1/hotel/catalog/room-types/{setup['room']['id']}/amenities",
        headers=setup["headers"],
        json=[
            {"code": "hair_dryer", "boolean_value": True},
            {"code": "tv_size_inches", "number_value": "55"},
        ],
    )
    assert response.status_code == 200, response.text

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            before = await session.scalar(select(func.count(RoomTypeAmenity.id)))
            service = AIActionOrchestrationService(session, FakeExtraction())
            tool = service.registry.get("get_room_catalog_facts")
            action, token = await service.propose(
                conversation,
                tool,
                {
                    "property_name": setup["property"]["name"],
                    "room_type_name": setup["room"]["name"],
                },
                idempotency_key="catalog-facts-1",
            )
            after = await session.scalar(select(func.count(RoomTypeAmenity.id)))
            amenities = {item["code"]: item for item in action.result["amenities"]}
            assert tool.classification is AIToolClassification.READ_ONLY
            assert tool.confirmation_required is False
            assert token is None
            assert action.status is AIToolActionStatus.SUCCEEDED
            assert amenities["hair_dryer"]["boolean_value"] is True
            assert amenities["tv_size_inches"]["number_value"] == "55.00"
            assert "internal_notes" not in action.result
            assert before == after

    asyncio.run(run())


def test_hold_requires_payload_bound_confirmation_and_is_idempotent(client_db):
    setup = _setup(client_db, "ai-hold@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            await _search(session, conversation, setup)
            service = AIActionOrchestrationService(session, FakeExtraction())
            action, token = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1, "quantity": 1},
                idempotency_key="hold-proposal-1",
            )
            assert action.status is AIToolActionStatus.AWAITING_CONFIRMATION
            assert token and action.result is None
            assert await session.scalar(select(func.count(Booking.id))) == 0
            first = await service.confirm(
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                action.id,
                token,
            )
            second = await service.confirm(
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                action.id,
                token,
            )
            assert first.id == second.id
            assert first.status is AIToolActionStatus.SUCCEEDED
            assert first.result["total_amount"] == "4500.75"
            assert await session.scalar(select(func.count(Booking.id))) == 1
            booking = await session.get(Booking, first.result_reference_id)
            assert booking.status is BookingStatus.HELD
            assert booking.source == "AI"
            assert booking.customer_id == conversation.customer_id
            assert booking.conversation_id == conversation.id
            booking_status, status_token = await service.propose(
                conversation,
                service.registry.get("get_booking_status"),
                {},
                idempotency_key="booking-status-1",
            )
            assert status_token is None
            assert booking_status.result["booking_status"] == "HELD"
            assert booking_status.result["payment_requires_review"] is False
            audits = list(
                (
                    await session.execute(
                        select(AIToolAuditEvent)
                        .where(AIToolAuditEvent.action_id == action.id)
                        .order_by(AIToolAuditEvent.created_at, AIToolAuditEvent.id)
                    )
                ).scalars()
            )
            assert [item.event_type for item in audits] == [
                AIToolAuditEventType.PROPOSED,
                AIToolAuditEventType.CONFIRMED,
                AIToolAuditEventType.EXECUTED,
            ]
            assert not await session.scalar(
                select(func.count(DomainEventOutbox.id)).where(
                    DomainEventOutbox.deduplication_key.like(f"%{action.id}%")
                )
            )

    asyncio.run(run())


def test_cancel_is_idempotent_and_concurrent_expiry_fails_closed(client_db):
    setup = _setup(client_db, "ai-cancel-expiry@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            await _search(session, conversation, setup)
            service = AIActionOrchestrationService(session, FakeExtraction())
            cancelled, _ = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="cancelled-hold",
            )
            first = await service.cancel(
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                cancelled.id,
            )
            second = await service.cancel(
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                cancelled.id,
            )
            assert first.id == second.id
            assert second.status is AIToolActionStatus.CANCELLED

            expired, token = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="expiry-race-hold",
            )
            expired.confirmation_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
            identity = (
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                expired.id,
            )

        async def confirm_expired():
            async with TestSessionLocal() as session:
                service = AIActionOrchestrationService(session, FakeExtraction())
                with pytest.raises(AIToolConfirmationError):
                    await service.confirm(*identity, token)

        await asyncio.gather(confirm_expired(), confirm_expired())
        async with TestSessionLocal() as session:
            stored = await session.get(AIToolAction, identity[-1])
            assert stored.status is AIToolActionStatus.EXPIRED
            expired_events = await session.scalar(
                select(func.count(AIToolAuditEvent.id)).where(
                    AIToolAuditEvent.action_id == stored.id,
                    AIToolAuditEvent.event_type == AIToolAuditEventType.EXPIRED,
                )
            )
            assert expired_events == 1
            assert await session.scalar(select(func.count(Booking.id))) == 0

    asyncio.run(run())


def test_altered_payload_and_expired_confirmation_fail_closed(client_db):
    setup = _setup(client_db, "ai-confirmation@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            await _search(session, conversation, setup)
            service = AIActionOrchestrationService(session, FakeExtraction())
            altered, altered_token = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="hold-altered",
            )
            altered.validated_args = {**altered.validated_args, "quantity": 2}
            await session.commit()
            with pytest.raises(AIToolConfirmationError):
                await service.confirm(
                    conversation.workspace_id,
                    conversation.id,
                    conversation.customer_id,
                    altered.id,
                    altered_token,
                )
            await session.rollback()

            expired, expired_token = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="hold-expired",
            )
            expired.confirmation_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
            with pytest.raises(AIToolConfirmationError):
                await service.confirm(
                    conversation.workspace_id,
                    conversation.id,
                    conversation.customer_id,
                    expired.id,
                    expired_token,
                )
            await session.rollback()
            refreshed = await session.get(AIToolAction, expired.id)
            assert refreshed.status is AIToolActionStatus.EXPIRED
            assert await session.scalar(select(func.count(Booking.id))) == 0

    asyncio.run(run())


def test_confirmation_is_conversation_customer_and_workspace_scoped(client_db):
    first = _setup(client_db, "ai-scope-first@example.com")
    second = _setup(client_db, "ai-scope-second@example.com")

    async def run():
        first_conversation = await _conversation(first)
        second_conversation = await _conversation(second)
        async with TestSessionLocal() as session:
            await _search(session, first_conversation, first)
            service = AIActionOrchestrationService(session, FakeExtraction())
            action, token = await service.propose(
                first_conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="scoped-hold",
            )
            action_id = action.id
            with pytest.raises(AIToolNotFoundError):
                await service.confirm(
                    second_conversation.workspace_id,
                    second_conversation.id,
                    second_conversation.customer_id,
                    action_id,
                    token,
                )
            await session.rollback()
            with pytest.raises(AIToolNotFoundError):
                await service.confirm(
                    first_conversation.workspace_id,
                    first_conversation.id,
                    second_conversation.customer_id,
                    action_id,
                    token,
                )

    asyncio.run(run())


def test_availability_change_is_revalidated_by_booking_service(client_db):
    setup = _setup(client_db, "ai-stale-availability@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            await _search(session, conversation, setup)
            service = AIActionOrchestrationService(session, FakeExtraction())
            action, token = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="stale-hold",
            )
            await session.execute(
                update(InventoryDate)
                .where(InventoryDate.workspace_id == setup["workspace_id"])
                .values(blocked_units=InventoryDate.total_units)
            )
            await session.commit()
            with pytest.raises(AIToolExecutionError) as failure:
                await service.confirm(
                    conversation.workspace_id,
                    conversation.id,
                    conversation.customer_id,
                    action.id,
                    token,
                )
            assert failure.value.details == {"reason": "BOOKING_UNAVAILABLE"}
            failed = await session.get(AIToolAction, action.id)
            assert failed.status is AIToolActionStatus.FAILED
            assert failed.error_code == "BOOKING_UNAVAILABLE"
            assert await session.scalar(select(func.count(Booking.id))) == 0

    asyncio.run(run())


def test_concurrent_confirmation_creates_one_hold(client_db):
    setup = _setup(client_db, "ai-concurrent@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            await _search(session, conversation, setup)
            service = AIActionOrchestrationService(session, FakeExtraction())
            action, token = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="concurrent-hold",
            )
            identity = (
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                action.id,
            )

        async def confirm_once():
            async with TestSessionLocal() as session:
                service = AIActionOrchestrationService(session, FakeExtraction())
                try:
                    result = await service.confirm(*identity, token)
                    return result.status.value
                except AIToolConfirmationError as exc:
                    return exc.code

        results = await asyncio.gather(confirm_once(), confirm_once())
        assert "SUCCEEDED" in results
        assert set(results).issubset({"SUCCEEDED", "AI_TOOL_CONFIRMATION_INVALID"})
        async with TestSessionLocal() as session:
            assert await session.scalar(select(func.count(Booking.id))) == 1
            stored = await session.get(AIToolAction, identity[-1])
            assert stored.status is AIToolActionStatus.SUCCEEDED

    asyncio.run(run())


def test_handoff_tool_reuses_existing_handoff_infrastructure(client_db):
    setup = _setup(client_db, "ai-handoff@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            conversation = await session.get(Conversation, conversation.id)
            service = AIActionOrchestrationService(session, FakeExtraction())
            action, token = await service.propose(
                conversation,
                service.registry.get("handoff_to_human"),
                {"reason": "customer_request"},
                idempotency_key="handoff-1",
            )
            await session.refresh(conversation)
            assert token is None
            assert action.status is AIToolActionStatus.SUCCEEDED
            assert conversation.ai_mode is ConversationMode.HUMAN
            assert conversation.needs_attention is True
            assert action.result["handoff_reason"] == "CUSTOMER_REQUEST"

    asyncio.run(run())


def test_payment_request_uses_booking_boundary_and_review_status_is_truthful(client_db):
    setup = _setup(client_db, "ai-payment@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            await _search(session, conversation, setup)
            service = AIActionOrchestrationService(session, FakeExtraction())
            hold, token = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="payment-hold",
            )
            hold = await service.confirm(
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                hold.id,
                token,
            )
            booking = await BookingService(session).advance_to_payment(
                conversation.workspace_id, None, hold.result_reference_id
            )
            destination = PaymentDestination(
                workspace_id=conversation.workspace_id,
                type=DestinationType.BANK_ACCOUNT,
                display_name="Main Bank",
                bank_name="Test Bank",
                account_name="ABC Hotel",
                account_number_masked="xxxx1234",
                is_active=True,
                is_default=True,
            )
            session.add(destination)
            await session.commit()
            payment_action, payment_token = await service.propose(
                conversation,
                service.registry.get("request_booking_payment"),
                {},
                idempotency_key="payment-request",
            )
            assert payment_action.status is AIToolActionStatus.AWAITING_CONFIRMATION
            payment_action = await service.confirm(
                conversation.workspace_id,
                conversation.id,
                conversation.customer_id,
                payment_action.id,
                payment_token,
            )
            assert payment_action.result["expected_amount"] == "4500.75"
            assert payment_action.result["destination_display_name"] == "Main Bank"
            payment = await session.get(Payment, payment_action.result_reference_id)
            payment.status = PaymentStatus.VERIFIED
            payment.verified_amount = booking.total_amount
            payment.booking_application_status = (
                PaymentApplicationStatus.REQUIRES_REVIEW
            )
            payment.booking_application_reason = (
                PaymentApplicationReason.BOOKING_EXPIRED
            )
            await session.commit()
            status_action, _ = await service.propose(
                conversation,
                service.registry.get("get_payment_status"),
                {},
                idempotency_key="payment-status",
            )
            assert status_action.result["requires_review"] is True
            assert status_action.result["review_reason"] == "BOOKING_EXPIRED"
            refreshed_booking = await session.get(Booking, booking.id)
            assert refreshed_booking.status is BookingStatus.PENDING_PAYMENT

    asyncio.run(run())


def _send_tool(client, setup, message_id, content):
    return client.post(
        (f"/api/v1/webchat/sessions/{setup['webchat']['conversation_id']}/messages"),
        headers={"X-WebChat-Token": setup["webchat"]["session_token"]},
        json={"client_message_id": message_id, "content": content},
    )


def test_webchat_tool_flow_uses_structured_state_and_confirmation(client_db):
    setup = _setup(client_db, "ai-webchat-flow@example.com")
    search = _send_tool(
        client_db,
        setup,
        "tool-search-1",
        (
            'action:ai_tool:search_availability:1 {"property_name":"ABC Hotel",'
            '"check_in":"2030-01-01","check_out":"2030-01-04",'
            '"adults":2,"children":0}'
        ),
    )
    assert search.status_code == 201, search.text
    search_data = search.json()["data"]["assistant"]
    assert search_data["type"] == "AI_TOOL_RESULT"
    assert search_data["ai_tool_action"]["tool_name"] == "search_availability"
    assert "4500.75" in search_data["message"]

    proposal = _send_tool(
        client_db,
        setup,
        "tool-hold-1",
        'action:ai_tool:create_booking_hold:1 {"option_index":1}',
    )
    assert proposal.status_code == 201, proposal.text
    proposal_data = proposal.json()["data"]["assistant"]
    assert proposal_data["type"] == "AI_TOOL_CONFIRMATION"
    assert proposal_data["ai_tool_action"]["confirmation_token"]

    confirmed = _send_tool(client_db, setup, "tool-hold-confirm", "yes")
    assert confirmed.status_code == 201, confirmed.text
    confirmed_data = confirmed.json()["data"]["assistant"]
    assert confirmed_data["type"] == "AI_TOOL_RESULT"
    assert confirmed_data["ai_tool_action"]["status"] == "SUCCEEDED"
    assert "4500.75" in confirmed_data["message"]

    repeated = _send_tool(client_db, setup, "tool-hold-confirm", "yes")
    assert repeated.status_code == 201
    assert repeated.json()["data"]["assistant"] == confirmed_data

    async def inspect():
        async with TestSessionLocal() as session:
            assert await session.scalar(select(func.count(Booking.id))) == 1
            assert await session.scalar(select(func.count(AIToolAction.id))) == 2

    asyncio.run(inspect())


def test_ai_action_observability_is_authenticated_and_workspace_scoped(client_db):
    first = _setup(client_db, "ai-observe-first@example.com")
    second = _setup(client_db, "ai-observe-second@example.com")

    async def seed():
        conversation = await _conversation(first)
        async with TestSessionLocal() as session:
            await _search(session, conversation, first)

    asyncio.run(seed())
    url = f"/api/v1/conversations/{first['webchat']['conversation_id']}/ai-actions"
    assert client_db.get(url).status_code == 401
    own = client_db.get(url, headers=first["headers"])
    assert own.status_code == 200
    assert own.json()["data"][0]["tool_name"] == "search_availability"
    serialized = str(own.json())
    assert "confirmation_token_hash" not in serialized
    assert "validated_args" not in serialized
    assert client_db.get(url, headers=second["headers"]).status_code == 404


def test_model_cannot_choose_workspace_or_customer_identifiers(client_db):
    setup = _setup(client_db, "ai-untrusted-ids@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            service = AIActionOrchestrationService(session, FakeExtraction())
            with pytest.raises(AIToolError) as failure:
                await service.propose(
                    conversation,
                    service.registry.get("search_availability"),
                    {
                        **_search_args(setup),
                        "workspace_id": str(uuid.uuid4()),
                        "customer_id": str(uuid.uuid4()),
                    },
                    idempotency_key="untrusted-identifiers",
                )
            assert getattr(failure.value, "code", None) == "AI_TOOL_INVALID"
            assert await session.scalar(select(func.count(AIToolAction.id))) == 0

    asyncio.run(run())


def test_human_mode_blocks_pending_confirmation_and_direct_tool_proposals(client_db):
    setup = _setup(client_db, "ai-human-policy@example.com")

    async def run():
        conversation = await _conversation(setup)
        async with TestSessionLocal() as session:
            await _search(session, conversation, setup)
            service = AIActionOrchestrationService(session, FakeExtraction())
            action, token = await service.propose(
                conversation,
                service.registry.get("create_booking_hold"),
                {"option_index": 1},
                idempotency_key="hold-before-human",
            )
            action_id = action.id
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation.id)
                .values(ai_mode=ConversationMode.HUMAN)
            )
            await session.commit()
            with pytest.raises(AIToolEligibilityError):
                await service.confirm(
                    conversation.workspace_id,
                    conversation.id,
                    conversation.customer_id,
                    action_id,
                    token,
                )
            await session.rollback()
            trusted = await session.get(Conversation, conversation.id)
            with pytest.raises(AIToolEligibilityError):
                await service.propose(
                    trusted,
                    service.registry.get("search_availability"),
                    _search_args(setup),
                    idempotency_key="human-search",
                )
            assert await session.scalar(select(func.count(Booking.id))) == 0

    asyncio.run(run())
