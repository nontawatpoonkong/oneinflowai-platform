"""Sprint 9.4 workspace analytics authorization and aggregation tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.channels import ChannelType
from app.models.action import (
    ActionActorType,
    ActionDefinition,
    ActionPriority,
    ActionRequest,
    ActionRequestStatus,
)
from app.models.ai_tool import (
    AIToolAction,
    AIToolActionStatus,
    AIToolClassification,
)
from app.models.automation import (
    AutomationDefinition,
    AutomationExecution,
    DomainEventOutbox,
)
from app.models.billing import PlanEntitlement
from app.models.booking import Booking, BookingStatus
from app.models.conversation import Conversation, ConversationMode, HandoffReason
from app.models.customer import Customer
from app.models.message import Message, MessageType, SenderType
from app.models.payment import (
    Payment,
    PaymentStatus,
    PaymentVerification,
    VerificationStatus,
)
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.entitlement import ANALYTICS_BASIC, EntitlementService
from app.services.promotion import PromotionService
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_booking import _hold, _payload, _setup
from tests.test_hotel import _auth
from tests.test_promotions import _promotion
from tests.test_stay import _booking, _physical_room, _set_confirmed, _stay

URL = "/api/v1/analytics/overview"


def test_promotion_analytics_are_confirmed_and_currency_separated(client_db):
    user, token, prop, room, plan = _setup(
        client_db, email="analytics-promotions@example.com"
    )
    campaign, _, code = _promotion(client_db, token, prop, room, plan)
    booking = _hold(
        client_db,
        token,
        _payload(prop, room, plan, promotion_code="WELCOME10"),
    ).json()["data"]
    workspace_id = uuid.UUID(user["workspace"]["id"])
    booking_id = uuid.UUID(booking["id"])

    async def confirm():
        async with TestSessionLocal() as session:
            stored = await session.get(Booking, booking_id)
            stored.status = BookingStatus.CONFIRMED
            await PromotionService(session).confirm_redemption(
                workspace_id, booking_id
            )
            await session.commit()

    asyncio.run(confirm())
    now = datetime.now(UTC)
    response = client_db.get(URL, headers=_auth(token), params=_range(now))
    assert response.status_code == 200, response.text
    metrics = response.json()["data"]["sales"]["promotions"]
    assert metrics["redemptions"] == 1
    assert metrics["by_currency"] == [
        {
            "currency": "THB",
            "uses": 1,
            "gross_amount": "4500.75",
            "discount_amount": "450.08",
            "net_amount": "4050.67",
        }
    ]
    assert metrics["campaigns"][0]["key"] == campaign["id"]
    assert metrics["campaigns"][0]["uses"] == 1
    assert metrics["codes"][0]["key"] == code["id"]
    assert metrics["sources"][0]["key"] == "MANUAL"


def _register(client: TestClient, email: str):
    data, token = register_verify_and_login(client, email=email)
    return data, {"Authorization": f"Bearer {token}"}


def _range(now):
    return {
        "start": (now - timedelta(days=3)).isoformat(),
        "end": (now + timedelta(days=1)).isoformat(),
    }


async def _role(workspace_id, role):
    async with TestSessionLocal() as session:
        member = await session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == uuid.UUID(workspace_id)
            )
        )
        member.role = role
        await session.commit()


async def _entitlement(workspace_id, enabled):
    async with TestSessionLocal() as session:
        subscription = await EntitlementService(session).latest_subscription(
            uuid.UUID(workspace_id)
        )
        item = await session.scalar(
            select(PlanEntitlement).where(
                PlanEntitlement.plan_id == subscription.plan_id,
                PlanEntitlement.key == ANALYTICS_BASIC,
            )
        )
        item.enabled = enabled
        await session.commit()


async def _seed(workspace_id: str, now: datetime):
    workspace_id = uuid.UUID(workspace_id)
    async with TestSessionLocal() as session:
        customer = Customer(workspace_id=workspace_id, display_name="Private Customer")
        session.add(customer)
        await session.flush()
        auto = Conversation(
            workspace_id=workspace_id,
            customer_id=customer.id,
            channel=ChannelType.WEB,
            ai_mode=ConversationMode.AUTO,
            created_at=now - timedelta(days=2),
        )
        handoff = Conversation(
            workspace_id=workspace_id,
            customer_id=customer.id,
            channel=ChannelType.LINE,
            ai_mode=ConversationMode.HUMAN,
            handoff_reason=HandoffReason.CUSTOMER_REQUEST,
            handoff_requested_at=now - timedelta(days=1),
            needs_attention=True,
            created_at=now - timedelta(days=1),
        )
        session.add_all([auto, handoff])
        await session.flush()
        session.add_all(
            [
                AIToolAction(
                    workspace_id=workspace_id,
                    conversation_id=auto.id,
                    customer_id=customer.id,
                    tool_name="hotel.search_availability",
                    tool_version="1",
                    classification=AIToolClassification.READ_ONLY,
                    status=AIToolActionStatus.SUCCEEDED,
                    validated_args={},
                    payload_hash="a" * 64,
                    confirmation_required=False,
                    idempotency_key="analytics-ai-success",
                    created_at=now - timedelta(days=1),
                ),
                AIToolAction(
                    workspace_id=workspace_id,
                    conversation_id=handoff.id,
                    customer_id=customer.id,
                    tool_name="hotel.create_booking_hold",
                    tool_version="1",
                    classification=AIToolClassification.MUTATING_REVERSIBLE,
                    status=AIToolActionStatus.FAILED,
                    validated_args={},
                    payload_hash="b" * 64,
                    confirmation_required=True,
                    idempotency_key="analytics-ai-failed",
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        session.add_all(
            [
                Message(
                    conversation_id=auto.id,
                    sender_type=SenderType.CUSTOMER,
                    content="secret customer text",
                    message_type=MessageType.TEXT,
                    created_at=now - timedelta(days=2),
                ),
                Message(
                    conversation_id=auto.id,
                    sender_type=SenderType.AI,
                    content="secret ai text",
                    message_type=MessageType.TEXT,
                    created_at=now - timedelta(days=2),
                ),
                Message(
                    conversation_id=handoff.id,
                    sender_type=SenderType.AGENT,
                    content="secret staff text",
                    message_type=MessageType.TEXT,
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        definition = ActionDefinition(
            workspace_id=workspace_id,
            key="booking",
            name="Booking",
            required_fields=[],
            optional_fields=[],
        )
        session.add(definition)
        await session.flush()
        session.add_all(
            [
                ActionRequest(
                    workspace_id=workspace_id,
                    action_definition_id=definition.id,
                    status=ActionRequestStatus.COMPLETED,
                    priority=ActionPriority.NORMAL,
                    payload={},
                    created_by_type=ActionActorType.HUMAN,
                    created_at=now - timedelta(days=1),
                    completed_at=now,
                ),
                ActionRequest(
                    workspace_id=workspace_id,
                    action_definition_id=definition.id,
                    status=ActionRequestStatus.WAITING,
                    priority=ActionPriority.NORMAL,
                    payload={},
                    created_by_type=ActionActorType.HUMAN,
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        from app.models.payment import DestinationType, PaymentDestination

        destination = PaymentDestination(
            workspace_id=workspace_id,
            type=DestinationType.BANK_ACCOUNT,
            display_name="Private account",
        )
        session.add(destination)
        await session.flush()
        verified = Payment(
            workspace_id=workspace_id,
            payment_destination_id=destination.id,
            expected_amount=Decimal("100.00"),
            verified_amount=Decimal("100.00"),
            currency="THB",
            status=PaymentStatus.VERIFIED,
            created_at=now - timedelta(days=1),
        )
        rejected = Payment(
            workspace_id=workspace_id,
            payment_destination_id=destination.id,
            expected_amount=Decimal("50.00"),
            currency="USD",
            status=PaymentStatus.REJECTED,
            created_at=now - timedelta(days=1),
        )
        session.add_all([verified, rejected])
        await session.flush()
        from app.models.payment import PaymentEvidence

        evidence = PaymentEvidence(
            workspace_id=workspace_id,
            payment_id=verified.id,
            storage_key="private/path",
            mime_type="image/jpeg",
            file_size=10,
            content_hash="a" * 64,
        )
        session.add(evidence)
        await session.flush()
        session.add(
            PaymentVerification(
                workspace_id=workspace_id,
                payment_id=verified.id,
                evidence_id=evidence.id,
                provider="easyslip_v2",
                status=VerificationStatus.VALID,
                reported_amount=Decimal("100.00"),
                currency="THB",
                receiver_match=True,
                amount_match=True,
                created_at=now - timedelta(days=1),
            )
        )
        automation = AutomationDefinition(
            workspace_id=workspace_id,
            name="Review alert",
            active=True,
            trigger_event_type="hotel.payment.requires_review",
            trigger_version=1,
            conditions=[],
            action_type="internal.notification",
            action_config={"title": "Review", "body": "Review payment"},
            schedule_mode="IMMEDIATE",
            schedule_config={},
        )
        session.add(automation)
        await session.flush()
        outboxes = [
            DomainEventOutbox(
                workspace_id=workspace_id,
                aggregate_type="Payment",
                aggregate_id=uuid.uuid4(),
                event_type="hotel.payment.requires_review",
                event_version=1,
                payload={},
                occurred_at=now - timedelta(days=1),
                available_at=now - timedelta(days=1),
                state="PROCESSED",
                attempt_count=0,
                deduplication_key=f"analytics-{index}",
            )
            for index in range(2)
        ]
        session.add_all(outboxes)
        await session.flush()
        session.add_all(
            [
                AutomationExecution(
                    workspace_id=workspace_id,
                    automation_id=automation.id,
                    event_id=outboxes[0].id,
                    status="SUCCEEDED",
                    scheduled_for=now - timedelta(days=1),
                    completed_at=now - timedelta(days=1),
                    attempt_count=1,
                    manual_retry_count=0,
                    terminal_failure=False,
                    effect_key="analytics-success",
                    created_at=now - timedelta(days=1),
                ),
                AutomationExecution(
                    workspace_id=workspace_id,
                    automation_id=automation.id,
                    event_id=outboxes[1].id,
                    status="FAILED",
                    scheduled_for=now - timedelta(days=1),
                    completed_at=now - timedelta(days=1),
                    attempt_count=3,
                    manual_retry_count=1,
                    terminal_failure=True,
                    effect_key="analytics-failed",
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        await session.commit()


def test_owner_admin_authorized_member_and_public_denied(client_db):
    now = datetime.now(UTC)
    data, headers = _register(client_db, "analytics-role@example.com")
    assert client_db.get(URL, headers=headers, params=_range(now)).status_code == 200
    asyncio.run(_role(data["workspace"]["id"], WorkspaceRole.ADMIN))
    assert client_db.get(URL, headers=headers, params=_range(now)).status_code == 200
    asyncio.run(_role(data["workspace"]["id"], WorkspaceRole.MEMBER))
    assert client_db.get(URL, headers=headers, params=_range(now)).status_code == 403
    assert client_db.get(URL, params=_range(now)).status_code == 401


def test_entitlement_denial_occurs_server_side(client_db):
    now = datetime.now(UTC)
    data, headers = _register(client_db, "analytics-entitlement@example.com")
    asyncio.run(_entitlement(data["workspace"]["id"], False))
    response = client_db.get(URL, headers=headers, params=_range(now))
    assert response.status_code == 403
    assert "kpis" not in response.text


def test_date_range_validation_and_empty_zero_series(client_db):
    data, headers = _register(client_db, "analytics-range@example.com")
    now = datetime.now(UTC)
    invalid = client_db.get(
        URL,
        headers=headers,
        params={"start": now.isoformat(), "end": now.isoformat()},
    )
    assert invalid.status_code == 422
    naive = client_db.get(
        URL,
        headers=headers,
        params={"start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00"},
    )
    assert naive.status_code == 422
    oversized = client_db.get(
        URL,
        headers=headers,
        params={
            "start": (now - timedelta(days=367)).isoformat(),
            "end": now.isoformat(),
        },
    )
    assert oversized.status_code == 422
    empty = client_db.get(URL, headers=headers, params=_range(now)).json()["data"]
    assert empty["kpis"]["conversations"] == 0
    assert len(empty["conversation_trend"]) == 5
    assert all(point["count"] == 0 for point in empty["conversation_trend"])
    assert data["workspace"]["id"] not in str(empty)


def test_workspace_scoped_operational_aggregates_and_privacy(client_db):
    now = datetime.now(UTC)
    first, first_headers = _register(client_db, "analytics-first@example.com")
    _, second_headers = _register(client_db, "analytics-second@example.com")
    asyncio.run(_seed(first["workspace"]["id"], now))
    result = client_db.get(URL, headers=first_headers, params=_range(now)).json()[
        "data"
    ]
    other = client_db.get(URL, headers=second_headers, params=_range(now)).json()[
        "data"
    ]
    assert result["kpis"] == {
        "unique_customers": 1,
        "conversations": 2,
        "customer_messages": 1,
        "ai_messages": 1,
        "staff_messages": 1,
        "ai_handled_conversations": 1,
        "ai_handled_rate": 50.0,
        "handoffs": 1,
        "handoff_rate": 50.0,
        "actions_created": 2,
        "actions_completed": 1,
        "action_completion_rate": 50.0,
        "payments_created": 2,
        "verified_payments": 1,
        "payment_verification_rate": 50.0,
    }
    assert {
        item["key"]: item["count"] for item in result["conversations_by_channel"]
    } == {"web": 1, "line": 1}
    assert result["current_queue"] == {
        "open_actions": 1,
        "unassigned_actions": 1,
        "conversations_needing_attention": 1,
    }
    assert result["verified_amounts"] == [{"currency": "THB", "amount": "100.00"}]
    assert result["verification_statuses"] == [
        {"key": "VALID", "label": None, "count": 1}
    ]
    assert other["kpis"]["conversations"] == 0
    assert result["ai_conversations"] == {
        "tool_actions": 2,
        "tool_action_statuses": {"FAILED": 1, "SUCCEEDED": 1},
        "tool_actions_succeeded": 1,
        "tool_actions_failed": 1,
        "human_handoffs": 1,
        "privacy": "No prompts, message bodies, reasoning, or provider metadata",
    }
    assert result["automation"]["execution_count"] == 2
    assert result["automation"]["statuses"] == {"FAILED": 1, "SUCCEEDED": 1}
    assert result["automation"]["success_rate"] == 50.0
    assert result["automation"]["retry_rate"] == 50.0
    assert result["automation"]["average_attempts"] == 2.0
    assert result["automation"]["terminal_failed"] == 1
    assert result["automation"]["most_used"][0]["count"] == 2
    serialized = str(result)
    for sensitive in ["secret", "Private", "storage_key", "content_hash", "account"]:
        assert sensitive not in serialized


def test_sales_analytics_separates_currency_and_counts_lifecycle(client_db):
    user, token, prop, room, plan = _setup(
        client_db, units=10, email="analytics-sales@example.com"
    )
    bookings = [
        _hold(
            client_db,
            token,
            _payload(prop, room, plan, key=f"analytics-sales-{index}"),
        ).json()["data"]
        for index in range(5)
    ]

    async def classify():
        values = [
            (BookingStatus.CONFIRMED, "THB", Decimal("100.00")),
            (BookingStatus.CONFIRMED, "THB", Decimal("300.00")),
            (BookingStatus.CONFIRMED, "USD", Decimal("50.00")),
            (BookingStatus.CANCELLED, "THB", Decimal("90.00")),
            (BookingStatus.EXPIRED, "THB", Decimal("80.00")),
        ]
        async with TestSessionLocal() as session:
            for booking, (status, currency, amount) in zip(
                bookings, values, strict=True
            ):
                await session.execute(
                    update(Booking)
                    .where(Booking.id == uuid.UUID(booking["id"]))
                    .values(
                        status=status,
                        currency=currency,
                        subtotal=amount,
                        total_amount=amount,
                    )
                )
            await session.commit()

    asyncio.run(classify())
    result = client_db.get(
        URL, headers=_auth(token), params=_range(datetime.now(UTC))
    ).json()["data"]["sales"]
    assert result["booking_counts"] == {
        "CANCELLED": 1,
        "CONFIRMED": 3,
        "EXPIRED": 1,
    }
    assert result["confirmed_value_by_currency"] == [
        {"currency": "THB", "amount": "400.00"},
        {"currency": "USD", "amount": "50.00"},
    ]
    assert result["average_confirmed_value_by_currency"] == [
        {"currency": "THB", "amount": "200.00"},
        {"currency": "USD", "amount": "50.00"},
    ]
    assert result["funnel"]["attribution_supported"] is False
    assert result["funnel"]["unsupported_stages"] == [
        "CONVERSATION",
        "AVAILABILITY_SEARCHED",
    ]
    assert user["workspace"]["id"] not in str(result)


def test_operations_analytics_uses_transition_and_housekeeping_events(client_db):
    _, token, prop, room_type, plan = _setup(
        client_db, units=2, email="analytics-operations@example.com"
    )
    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)
    checked_in = client_db.post(
        f"/api/v1/hotel/stays/{stay['id']}/check-in",
        headers=_auth(token),
        json={"room_ids": [room["id"]]},
    )
    assert checked_in.status_code == 200
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-out", headers=_auth(token)
        ).status_code
        == 200
    )
    task = client_db.get(
        "/api/v1/hotel/housekeeping/tasks", headers=_auth(token)
    ).json()["data"]["items"][0]
    assert (
        client_db.post(
            f"/api/v1/hotel/housekeeping/tasks/{task['id']}/start",
            headers=_auth(token),
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/housekeeping/tasks/{task['id']}/complete",
            headers=_auth(token),
        ).status_code
        == 200
    )
    result = client_db.get(
        URL, headers=_auth(token), params=_range(datetime.now(UTC))
    ).json()["data"]["operations"]
    assert result["stays"] == {"CHECKED_IN": 1, "CHECKED_OUT": 1}
    assert result["room_readiness"]["READY"] == 1
    assert result["housekeeping_completed"] == 1
    assert result["housekeeping_turnaround_minutes"] is not None
    assert result["housekeeping_turnaround_minutes"] >= 0
