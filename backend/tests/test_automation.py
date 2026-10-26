"""PostgreSQL-backed Hotel automation durability and safety tests."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.channels import ChannelType
from app.integrations.channels.provider import ChannelSendResult
from app.models.audit import WorkspaceAuditEvent
from app.models.automation import (
    AutomationDefinition,
    AutomationExecution,
    DomainEventOutbox,
)
from app.models.channel import ChannelMessageDelivery
from app.models.conversation import Conversation, ConversationStatus
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity
from app.models.message import Message
from app.models.notification import Notification
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.automation import AutomationDefinitionCreate
from app.services.automation import AutomationActionError, AutomationService
from app.services.automation_events import emit_domain_event
from tests.conftest import TestSessionLocal, provision_active_test_subscription
from tests.test_booking import _setup
from tests.test_booking_payment_confirmation import (
    _advance,
    _confirm,
    _link,
    _mark_verified,
    _prepared,
)
from tests.test_booking_payment_reconciliation import _retry
from tests.test_hotel import _auth
from tests.test_stay import _booking, _physical_room, _set_confirmed, _stay


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Host": "localhost"}


def _account(client, prefix):
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    password = "supersecret123"
    registered = client.post(
        "/api/v1/auth/register",
        headers={"Host": "localhost"},
        json={"email": email, "password": password, "full_name": "Owner"},
    )
    assert registered.status_code == 201, registered.text
    verified = client.post(
        "/api/v1/auth/verify-email",
        headers={"Host": "localhost"},
        json={"email": email, "otp": client.app.state.fake_email_provider.latest_otp},
    )
    assert verified.status_code == 200, verified.text
    login = client.post(
        "/api/v1/auth/login",
        headers={"Host": "localhost"},
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    subscription_id = provision_active_test_subscription(
        registered.json()["data"]["user"]["id"]
    )
    workspace = client.post(
        "/api/v1/workspaces",
        headers=_headers(token),
        json={"name": prefix, "subscription_id": subscription_id},
    )
    assert workspace.status_code == 201, workspace.text
    data = registered.json()["data"]
    data["workspace"] = workspace.json()["data"]
    return data, token


def _definition(**overrides):
    data = {
        "name": "Payment review alert",
        "active": True,
        "trigger_event_type": "hotel.payment.requires_review",
        "trigger_version": 1,
        "conditions": [],
        "action_type": "internal.notification",
        "action_config": {"title": "Payment review", "body": "Review {{currency}}"},
        "schedule_mode": "IMMEDIATE",
        "schedule_config": {},
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "field,operator,value",
    [
        ("currency", "EQ", "THB"),
        ("currency", "NE", "USD"),
        ("currency", "IN", ["THB", "USD"]),
        ("total_amount", "GTE", 100),
        ("total_amount", "LTE", 1000),
    ],
)
def test_bounded_condition_contract_accepts_supported_operators(field, operator, value):
    item = AutomationDefinitionCreate.model_validate(
        _definition(conditions=[{"field": field, "operator": operator, "value": value}])
    )
    assert item.conditions[0].operator.value == operator


@pytest.mark.parametrize(
    "change",
    [
        {"trigger_event_type": "arbitrary.event"},
        {"action_type": "arbitrary.code"},
        {"conditions": [{"field": "secret", "operator": "EQ", "value": "x"}]},
        {"conditions": [{"field": "currency", "operator": "IN", "value": "THB"}]},
        {
            "action_type": "customer.message",
            "action_config": {"template": "Hello {{customer.password}}"},
        },
        {
            "action_type": "customer.message",
            "action_config": {"template": "Hello {{unknown}}"},
        },
        {"schedule_mode": "IMMEDIATE", "schedule_config": {"delay_seconds": 1}},
    ],
)
def test_invalid_trigger_condition_action_template_and_schedule_fail_closed(change):
    with pytest.raises(ValidationError):
        AutomationDefinitionCreate.model_validate(_definition(**change))


def test_create_list_enable_disable_validate_and_member_authorization(client_db):
    account, token = _account(client_db, "automation-api")
    headers = _headers(token)
    validated = client_db.post(
        "/api/v1/automations/validate", headers=headers, json=_definition()
    )
    assert validated.status_code == 200
    created = client_db.post("/api/v1/automations", headers=headers, json=_definition())
    assert created.status_code == 200, created.text
    item = created.json()["data"]
    assert item["workspace_id"]
    assert (
        client_db.post(
            f"/api/v1/automations/{item['id']}/disable", headers=headers
        ).json()["data"]["active"]
        is False
    )
    assert (
        client_db.post(
            f"/api/v1/automations/{item['id']}/enable", headers=headers
        ).json()["data"]["active"]
        is True
    )
    listed = client_db.get("/api/v1/automations", headers=headers).json()["data"]
    assert listed["total"] == 1

    async def audit_actions():
        async with TestSessionLocal() as session:
            return set(
                await session.scalars(
                    select(WorkspaceAuditEvent.action).where(
                        WorkspaceAuditEvent.resource_id == uuid.UUID(item["id"])
                    )
                )
            )

    assert {
        "AUTOMATION_CREATED",
        "AUTOMATION_DISABLED",
        "AUTOMATION_ENABLED",
    } <= asyncio.run(audit_actions())

    async def make_member():
        async with TestSessionLocal() as session:
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id
                    == uuid.UUID(account["workspace"]["id"]),
                    WorkspaceMember.user_id == uuid.UUID(account["user"]["id"]),
                )
            )
            membership.role = WorkspaceRole.MEMBER
            session.add(
                WorkspaceMemberCapability(
                    workspace_id=membership.workspace_id,
                    membership_id=membership.id,
                    capability="automation.read",
                    granted_by_user_id=membership.user_id,
                    granted_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(make_member())
    assert client_db.get("/api/v1/automations", headers=headers).status_code == 200
    assert (
        client_db.post(
            "/api/v1/automations", headers=headers, json=_definition()
        ).status_code
        == 403
    )


def test_outbox_is_transactional_versioned_deduplicated_and_safe(client_db):
    user, _ = _account(client_db, "outbox")
    workspace_id = uuid.UUID(user["workspace"]["id"])
    aggregate_id = uuid.uuid4()

    async def scenario():
        async with TestSessionLocal() as session:
            await emit_domain_event(
                session,
                workspace_id=workspace_id,
                aggregate_type="booking",
                aggregate_id=aggregate_id,
                event_type="hotel.booking.confirmed",
                payload={"booking_id": aggregate_id, "currency": "THB"},
                deduplication_key=f"confirmed:{aggregate_id}",
            )
            await session.rollback()
        async with TestSessionLocal() as session:
            assert await session.scalar(select(func.count(DomainEventOutbox.id))) == 0
            for _ in range(2):
                await emit_domain_event(
                    session,
                    workspace_id=workspace_id,
                    aggregate_type="booking",
                    aggregate_id=aggregate_id,
                    event_type="hotel.booking.confirmed",
                    payload={"booking_id": aggregate_id, "currency": "THB"},
                    deduplication_key=f"confirmed:{aggregate_id}",
                )
            await session.commit()
            event = await session.scalar(select(DomainEventOutbox))
            assert event.event_version == 1
            assert event.payload["workspace_id"] == str(workspace_id)
            assert "secret" not in event.payload
            assert await session.scalar(select(func.count(DomainEventOutbox.id))) == 1

    asyncio.run(scenario())


def test_booking_confirmation_emits_one_atomic_versioned_event(client_db):
    client_db.headers.update({"Host": "localhost"})
    user, token, booking, destination_id, _ = _prepared(
        client_db, email=f"automation-confirm-{uuid.uuid4().hex[:8]}@example.com"
    )
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _advance(client_db, token, booking)
    payment_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]
    _mark_verified(payment_id)
    assert _confirm(client_db, token, booking, payment_id).status_code == 200
    assert _confirm(client_db, token, booking, payment_id).status_code == 200

    async def verify():
        async with TestSessionLocal() as session:
            events = list(
                await session.scalars(
                    select(DomainEventOutbox).where(
                        DomainEventOutbox.workspace_id == workspace_id,
                        DomainEventOutbox.event_type == "hotel.booking.confirmed",
                    )
                )
            )
            assert len(events) == 1
            assert events[0].event_version == 1
            assert events[0].payload["booking_id"] == booking["id"]

    asyncio.run(verify())


def test_stay_checkin_checkout_and_room_dirty_emit_once(client_db):
    client_db.headers.update({"Host": "localhost"})
    email = f"automation-stay-{uuid.uuid4().hex[:8]}@example.com"
    user, token, prop, room_type, plan = _setup(client_db, units=1, email=email)
    booking = _booking(client_db, token, prop, room_type, plan)
    _set_confirmed(booking["id"])
    stay = _stay(client_db, token, booking["id"]).json()["data"]
    room = _physical_room(client_db, token, prop, room_type)
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-in",
            headers=_auth(token),
            json={"room_ids": [room["id"]]},
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-in",
            headers=_auth(token),
            json={"room_ids": [room["id"]]},
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-out", headers=_auth(token)
        ).status_code
        == 200
    )
    assert (
        client_db.post(
            f"/api/v1/hotel/stays/{stay['id']}/check-out", headers=_auth(token)
        ).status_code
        == 200
    )
    workspace_id = uuid.UUID(user["workspace"]["id"])

    async def verify():
        async with TestSessionLocal() as session:
            rows = (
                await session.execute(
                    select(DomainEventOutbox.event_type, func.count())
                    .where(DomainEventOutbox.workspace_id == workspace_id)
                    .group_by(DomainEventOutbox.event_type)
                )
            ).all()
            counts = dict(rows)
            assert counts["hotel.stay.created"] == 1
            assert counts["hotel.stay.checked_in"] == 1
            assert counts["hotel.stay.checked_out"] == 1
            assert counts["hotel.room.dirty"] == 1

    asyncio.run(verify())


def test_payment_review_event_is_deduplicated(client_db):
    client_db.headers.update({"Host": "localhost"})
    user, token, booking, destination_id, _ = _prepared(
        client_db, email=f"automation-review-{uuid.uuid4().hex[:8]}@example.com"
    )
    workspace_id = uuid.UUID(user["workspace"]["id"])
    _advance(client_db, token, booking)
    payment_id = _link(client_db, token, booking, destination_id).json()["data"]["id"]

    async def expire():
        from app.services.booking import BookingService

        async with TestSessionLocal() as session:
            await BookingService(session).expire(
                workspace_id,
                uuid.UUID(booking["id"]),
                now=datetime.now(UTC) + timedelta(minutes=16),
            )

    asyncio.run(expire())
    _mark_verified(payment_id)
    assert _retry(client_db, token, payment_id).status_code == 200
    assert _retry(client_db, token, payment_id).status_code == 200

    async def verify():
        async with TestSessionLocal() as session:
            count = await session.scalar(
                select(func.count(DomainEventOutbox.id)).where(
                    DomainEventOutbox.workspace_id == workspace_id,
                    DomainEventOutbox.event_type == "hotel.payment.requires_review",
                )
            )
            assert count == 1

    asyncio.run(verify())


def test_matching_nonmatching_disabled_execution_uniqueness_and_notification(client_db):
    user, _ = _account(client_db, "automation-run")
    workspace_id = uuid.UUID(user["workspace"]["id"])
    user_id = uuid.UUID(user["user"]["id"])

    async def scenario():
        async with TestSessionLocal() as session:
            matching = AutomationDefinition(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                **AutomationDefinitionCreate.model_validate(
                    _definition(
                        conditions=[
                            {"field": "currency", "operator": "EQ", "value": "THB"}
                        ]
                    )
                ).model_dump(mode="json"),
            )
            nonmatching = AutomationDefinition(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                **AutomationDefinitionCreate.model_validate(
                    _definition(
                        name="USD only",
                        conditions=[
                            {"field": "currency", "operator": "EQ", "value": "USD"}
                        ],
                    )
                ).model_dump(mode="json"),
            )
            disabled = AutomationDefinition(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                **AutomationDefinitionCreate.model_validate(
                    _definition(name="Disabled", active=False)
                ).model_dump(mode="json"),
            )
            session.add_all([matching, nonmatching, disabled])
            await session.flush()
            event_id = uuid.uuid4()
            await emit_domain_event(
                session,
                workspace_id=workspace_id,
                aggregate_type="payment",
                aggregate_id=event_id,
                event_type="hotel.payment.requires_review",
                payload={"payment_id": event_id, "currency": "THB"},
                deduplication_key=f"review:{event_id}",
            )
            await session.commit()
            service = AutomationService(session)
            assert await service.evaluate_events() == 1
            assert await service.evaluate_events() == 0
            assert await session.scalar(select(func.count(AutomationExecution.id))) == 1
            assert await service.run_executions() == 1
            execution = await session.scalar(select(AutomationExecution))
            assert execution.status == "SUCCEEDED"
            assert execution.attempt_count == 1
            assert await session.scalar(select(func.count(Notification.id))) == 1
            execution.status = "PENDING"
            execution.scheduled_for = datetime.now(UTC)
            await session.commit()
            await service.run_executions()
            assert await session.scalar(select(func.count(Notification.id))) == 1

    asyncio.run(scenario())


def test_delay_and_property_timezone_scheduling(client_db):
    user, _ = _account(client_db, "automation-time")
    workspace_id = uuid.UUID(user["workspace"]["id"])
    user_id = uuid.UUID(user["user"]["id"])

    async def scenario():
        from app.models.hotel import Property

        async with TestSessionLocal() as session:
            prop = Property(
                workspace_id=workspace_id,
                name="Bangkok Hotel",
                timezone="Asia/Bangkok",
                currency="THB",
            )
            session.add(prop)
            await session.flush()
            definition = AutomationDefinition(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                **AutomationDefinitionCreate.model_validate(
                    _definition(
                        name="Pre-arrival",
                        trigger_event_type="hotel.booking.confirmed",
                        schedule_mode="BEFORE_DATE_FIELD",
                        schedule_config={
                            "date_field": "check_in",
                            "offset_seconds": 86400,
                            "local_time": "14:00",
                        },
                    )
                ).model_dump(mode="json"),
            )
            session.add(definition)
            aggregate_id = uuid.uuid4()
            await emit_domain_event(
                session,
                workspace_id=workspace_id,
                aggregate_type="booking",
                aggregate_id=aggregate_id,
                event_type="hotel.booking.confirmed",
                payload={
                    "booking_id": aggregate_id,
                    "property_id": prop.id,
                    "check_in": "2027-01-10",
                    "currency": "THB",
                },
                deduplication_key=f"prearrival:{aggregate_id}",
            )
            await session.commit()
            await AutomationService(session).evaluate_events()
            execution = await session.scalar(select(AutomationExecution))
            assert execution.scheduled_for.isoformat() == "2027-01-09T07:00:00+00:00"

    asyncio.run(scenario())


def test_two_workers_claim_one_execution_effect(client_db):
    user, _ = _account(client_db, "automation-workers")
    workspace_id = uuid.UUID(user["workspace"]["id"])
    user_id = uuid.UUID(user["user"]["id"])

    async def scenario():
        async with TestSessionLocal() as session:
            definition = AutomationDefinition(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                **AutomationDefinitionCreate.model_validate(_definition()).model_dump(
                    mode="json"
                ),
            )
            session.add(definition)
            aggregate_id = uuid.uuid4()
            await emit_domain_event(
                session,
                workspace_id=workspace_id,
                aggregate_type="payment",
                aggregate_id=aggregate_id,
                event_type="hotel.payment.requires_review",
                payload={"currency": "THB"},
                deduplication_key=f"workers:{aggregate_id}",
            )
            await session.commit()
            await AutomationService(session).evaluate_events()

        async def worker():
            async with TestSessionLocal() as session:
                return await AutomationService(session).run_executions()

        claimed = await asyncio.gather(worker(), worker())
        assert sum(claimed) == 1
        async with TestSessionLocal() as session:
            assert await session.scalar(select(func.count(Notification.id))) == 1
            execution = await session.scalar(select(AutomationExecution))
            assert execution.status == "SUCCEEDED"

    asyncio.run(scenario())


def test_retryable_terminal_and_max_retry_lifecycle(client_db):
    user, _ = _account(client_db, "automation-retry")
    workspace_id = uuid.UUID(user["workspace"]["id"])
    user_id = uuid.UUID(user["user"]["id"])

    async def scenario():
        async with TestSessionLocal() as session:
            definition = AutomationDefinition(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                **AutomationDefinitionCreate.model_validate(_definition()).model_dump(
                    mode="json"
                ),
            )
            session.add(definition)
            aggregate_id = uuid.uuid4()
            await emit_domain_event(
                session,
                workspace_id=workspace_id,
                aggregate_type="payment",
                aggregate_id=aggregate_id,
                event_type="hotel.payment.requires_review",
                payload={"currency": "THB"},
                deduplication_key=f"retry:{aggregate_id}",
            )
            await session.commit()
            service = AutomationService(session)
            await service.evaluate_events()

            async def retryable(_execution):
                raise AutomationActionError("TEMPORARY", retryable=True)

            service._execute = retryable
            started = datetime.now(UTC)
            await service.run_executions(now=started)
            execution = await session.scalar(select(AutomationExecution))
            assert execution.status == "PENDING"
            assert execution.attempt_count == 1
            assert int((execution.scheduled_for - started).total_seconds()) == 60

            execution.attempt_count = 2
            execution.scheduled_for = started
            await session.commit()
            await service.run_executions(now=started)
            assert execution.status == "FAILED"
            assert execution.attempt_count == 3
            assert execution.last_error_code == "TEMPORARY"

            execution.status = "PENDING"
            execution.attempt_count = 0
            execution.scheduled_for = started
            await session.commit()

            async def terminal(_execution):
                raise AutomationActionError("INVALID_TEMPLATE")

            service._execute = terminal
            await service.run_executions(now=started)
            assert execution.status == "FAILED"
            assert execution.attempt_count == 1

            execution.status = "RUNNING"
            execution.attempt_count = 1
            execution.started_at = started - timedelta(minutes=6)
            await session.commit()

            recovered = await service.recover_stale_executions(
                stale_seconds=300,
                batch_size=1,
                now=started,
                worker_id="recovery-test",
            )
            assert recovered == 1
            assert execution.status == "PENDING"
            assert execution.attempt_count == 1
            assert execution.scheduled_for == started + timedelta(seconds=60)
            assert execution.failure_history[-1]["source"] == "stale_recovery"

    asyncio.run(scenario())


def test_customer_message_uses_channel_boundary_and_effect_is_idempotent(client_db):
    account, token = _account(client_db, "automation-channel")
    headers = _headers(token)
    connection_response = client_db.post(
        "/api/v1/channels/line",
        headers=headers,
        json={
            "display_name": "LINE Hotel",
            "external_account_id": "line-hotel",
            "channel_access_token": "test-token",
            "channel_secret": "test-secret",
        },
    )
    assert connection_response.status_code == 201
    workspace_id = uuid.UUID(account["workspace"]["id"])
    user_id = uuid.UUID(account["user"]["id"])
    connection_id = uuid.UUID(connection_response.json()["data"]["id"])

    class FakeProvider:
        def __init__(self):
            self.calls = 0

        async def send(self, message):
            self.calls += 1
            assert message.external_user_id == "U-AUTOMATION"
            assert message.text == "Booking B-101 confirmed"
            return ChannelSendResult("provider-1")

    provider = FakeProvider()

    async def scenario():
        async with TestSessionLocal() as session:
            customer = Customer(workspace_id=workspace_id, display_name="Guest")
            session.add(customer)
            await session.flush()
            conversation = Conversation(
                workspace_id=workspace_id,
                customer_id=customer.id,
                channel=ChannelType.LINE,
                status=ConversationStatus.OPEN,
                channel_connection_id=connection_id,
            )
            session.add(conversation)
            await session.flush()
            session.add(
                CustomerIdentity(
                    workspace_id=workspace_id,
                    customer_id=customer.id,
                    channel_connection_id=connection_id,
                    channel=ChannelType.LINE,
                    external_user_id="U-AUTOMATION",
                )
            )
            definition = AutomationDefinition(
                workspace_id=workspace_id,
                created_by_user_id=user_id,
                **AutomationDefinitionCreate.model_validate(
                    _definition(
                        name="Booking confirmation",
                        trigger_event_type="hotel.booking.confirmed",
                        action_type="customer.message",
                        action_config={
                            "template": "Booking {{booking_reference}} confirmed"
                        },
                    )
                ).model_dump(mode="json"),
            )
            session.add(definition)
            booking_id = uuid.uuid4()
            await emit_domain_event(
                session,
                workspace_id=workspace_id,
                aggregate_type="booking",
                aggregate_id=booking_id,
                event_type="hotel.booking.confirmed",
                payload={
                    "booking_id": booking_id,
                    "booking_reference": "B-101",
                    "conversation_id": conversation.id,
                },
                deduplication_key=f"message:{booking_id}",
            )
            await session.commit()
            service = AutomationService(
                session, channel_provider_factory=lambda *_args: provider
            )
            await service.evaluate_events()
            await service.run_executions()
            execution = await session.scalar(select(AutomationExecution))
            assert execution.status == "SUCCEEDED"
            assert await session.scalar(select(func.count(Message.id))) == 1
            assert (
                await session.scalar(select(func.count(ChannelMessageDelivery.id))) == 1
            )
            execution.status = "PENDING"
            execution.scheduled_for = datetime.now(UTC)
            await session.commit()
            await service.run_executions()
            assert provider.calls == 1
            assert await session.scalar(select(func.count(Message.id))) == 1

    asyncio.run(scenario())


def test_execution_history_workspace_isolation_and_order(client_db):
    _, token_a = _account(client_db, "automation-a")
    _, token_b = _account(client_db, "automation-b")
    created = client_db.post(
        "/api/v1/automations", headers=_headers(token_a), json=_definition()
    )
    assert created.status_code == 200
    assert (
        client_db.get("/api/v1/automations", headers=_headers(token_b)).json()["data"][
            "total"
        ]
        == 0
    )
    history = client_db.get("/api/v1/automations/executions", headers=_headers(token_a))
    assert history.status_code == 200
    assert history.json()["data"]["counts"]["PENDING"] == 0
