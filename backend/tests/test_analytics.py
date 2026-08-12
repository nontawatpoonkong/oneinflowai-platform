"""Sprint 9.4 workspace analytics authorization and aggregation tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.channels import ChannelType
from app.models.action import (
    ActionActorType,
    ActionDefinition,
    ActionPriority,
    ActionRequest,
    ActionRequestStatus,
)
from app.models.billing import PlanEntitlement
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
from tests.conftest import TestSessionLocal, register_verify_and_login

URL = "/api/v1/analytics/overview"


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
    serialized = str(result)
    for sensitive in ["secret", "Private", "storage_key", "content_hash", "account"]:
        assert sensitive not in serialized
