"""F-C1: AI tool results follow the capability of the data they carry.

GET /conversations/{id}/ai-actions needs conversation.read, but each tool's
typed result belongs to another domain: availability and room facts need
room.read, booking holds need booking.read, booking status, payment requests
and payment status carry booking and payment data and need both, and handoff
results need nothing beyond conversation.read. Results a caller may not read
are withheld (``result`` null, ``result_visible`` false).
"""

import asyncio

from sqlalchemy import func, select

from app.ai_tools import create_ai_tool_registry
from app.ai_tools.result_access import RESULT_CAPABILITIES
from app.models.ai_tool import AIToolAction
from app.models.audit import WorkspaceAuditEvent
from app.models.booking import Booking
from app.models.payment import (
    DestinationType,
    Payment,
    PaymentApplicationReason,
    PaymentApplicationStatus,
    PaymentDestination,
    PaymentStatus,
)
from app.models.workspace_member import WorkspaceRole
from app.services.booking import BookingService
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_ai_action_orchestration import _send_tool, _setup
from tests.test_hotel import _auth
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

# Values that only booking or payment readers may see.
BOOKING_TOTAL = "4500.75"
DESTINATION_MASK = "xxxx1234"
DESTINATION_NAME = "Main Bank"
REVIEW_REASON = "BOOKING_EXPIRED"
STAY_DATE = "2030-01-01"
TOOLS = (
    "search_availability",
    "create_booking_hold",
    "get_booking_status",
    "request_booking_payment",
    "get_payment_status",
)


def _tool(client, setup, key, content):
    response = _send_tool(client, setup, key, content)
    assert response.status_code == 201, response.text
    return response.json()["data"]["assistant"]


def _ai_tool_world(client, email):
    """A WebChat guest who searched, held, requested and checked a payment."""

    setup = _setup(client, email)
    _tool(
        client,
        setup,
        "fc1-search",
        'action:ai_tool:search_availability:1 {"property_name":"ABC Hotel",'
        f'"check_in":"{STAY_DATE}","check_out":"2030-01-04",'
        '"adults":2,"children":0}',
    )
    _tool(
        client,
        setup,
        "fc1-hold",
        'action:ai_tool:create_booking_hold:1 {"option_index":1}',
    )
    held = _tool(client, setup, "fc1-hold-yes", "yes")
    assert held["ai_tool_action"]["status"] == "SUCCEEDED", held

    async def prepare_payment():
        async with TestSessionLocal() as session:
            booking = await session.scalar(
                select(Booking).where(Booking.workspace_id == setup["workspace_id"])
            )
            await BookingService(session).advance_to_payment(
                setup["workspace_id"], None, booking.id
            )
            session.add(
                PaymentDestination(
                    workspace_id=setup["workspace_id"],
                    type=DestinationType.BANK_ACCOUNT,
                    display_name=DESTINATION_NAME,
                    bank_name="Test Bank",
                    account_name="ABC Hotel",
                    account_number_masked=DESTINATION_MASK,
                    is_active=True,
                    is_default=True,
                )
            )
            await session.commit()

    asyncio.run(prepare_payment())
    _tool(client, setup, "fc1-pay", "action:ai_tool:request_booking_payment:1 {}")
    paid = _tool(client, setup, "fc1-pay-yes", "yes")
    assert paid["ai_tool_action"]["status"] == "SUCCEEDED", paid

    async def verify_for_review():
        async with TestSessionLocal() as session:
            payment = await session.scalar(
                select(Payment).where(Payment.workspace_id == setup["workspace_id"])
            )
            payment.status = PaymentStatus.VERIFIED
            payment.verified_amount = payment.expected_amount
            payment.booking_application_status = (
                PaymentApplicationStatus.REQUIRES_REVIEW
            )
            payment.booking_application_reason = (
                PaymentApplicationReason.BOOKING_EXPIRED
            )
            await session.commit()

    asyncio.run(verify_for_review())
    _tool(client, setup, "fc1-status", "action:ai_tool:get_booking_status:1 {}")
    _tool(client, setup, "fc1-payment-status", "action:ai_tool:get_payment_status:1 {}")
    setup["path"] = (
        f"/api/v1/conversations/{setup['webchat']['conversation_id']}/ai-actions"
    )
    return setup


def _member(client, setup, email, capabilities):
    user, token = _zero_workspace_account(client, email)
    workspace_id = str(setup["workspace_id"])
    membership_id = _add_member(workspace_id, user["id"], WorkspaceRole.MEMBER)
    _grant(client, setup, membership_id, capabilities)
    return _headers(token, workspace_id), membership_id


def _grant(client, setup, membership_id, capabilities):
    granted = client.put(
        f"/api/v1/workspaces/{setup['workspace_id']}/members/{membership_id}/capabilities",
        headers=_headers(setup["token"]),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text


def _results(client, setup, headers):
    response = client.get(setup["path"], headers=headers)
    assert response.status_code == 200, response.text
    items = response.json()["data"]
    assert sorted(item["tool_name"] for item in items) == sorted(TOOLS)
    return response, {item["tool_name"]: item for item in items}


def _assert_visible(items, visible):
    for name in TOOLS:
        item = items[name]
        assert item["status"] == "SUCCEEDED", item
        if name in visible:
            assert item["result"], name
            assert item["result_visible"] is True, name
        else:
            assert item["result"] is None, name
            assert item["result_visible"] is False, name


def _state(setup):
    async def read():
        async with TestSessionLocal() as session:
            scope = setup["workspace_id"]
            actions = await session.execute(
                select(AIToolAction.id, AIToolAction.status, AIToolAction.updated_at)
                .where(AIToolAction.workspace_id == scope)
                .order_by(AIToolAction.id)
            )
            audit = await session.scalar(
                select(func.count())
                .select_from(WorkspaceAuditEvent)
                .where(WorkspaceAuditEvent.workspace_id == scope)
            )
            return [tuple(row) for row in actions.all()], audit

    return asyncio.run(read())


def test_conversation_read_alone_sees_no_booking_or_payment_results(client_db):
    setup = _ai_tool_world(client_db, "fc1-conversation@example.com")
    member, _ = _member(
        client_db, setup, "fc1-conv-only@example.com", ["conversation.read"]
    )
    before = _state(setup)
    response, items = _results(client_db, setup, member)
    for value in (
        BOOKING_TOTAL,
        DESTINATION_MASK,
        DESTINATION_NAME,
        REVIEW_REASON,
        STAY_DATE,
    ):
        assert value not in response.text, value
    _assert_visible(items, visible=set())
    assert _state(setup) == before


def test_booking_and_payment_reads_unlock_only_their_results(client_db):
    setup = _ai_tool_world(client_db, "fc1-partial@example.com")
    booking_only, _ = _member(
        client_db,
        setup,
        "fc1-booking@example.com",
        ["conversation.read", "booking.read"],
    )
    response, items = _results(client_db, setup, booking_only)
    _assert_visible(items, visible={"create_booking_hold"})
    assert items["create_booking_hold"]["result"]["total_amount"] == BOOKING_TOTAL
    for value in (DESTINATION_MASK, DESTINATION_NAME, REVIEW_REASON):
        assert value not in response.text, value

    payment_only, _ = _member(
        client_db,
        setup,
        "fc1-payment@example.com",
        ["conversation.read", "payment.read"],
    )
    response, items = _results(client_db, setup, payment_only)
    # Every payment result also names booking state, so booking.read is needed too.
    _assert_visible(items, visible=set())
    for value in (BOOKING_TOTAL, DESTINATION_MASK, REVIEW_REASON, STAY_DATE):
        assert value not in response.text, value


def test_full_readers_and_owner_see_every_result_until_revoked(client_db):
    setup = _ai_tool_world(client_db, "fc1-full@example.com")
    member, membership_id = _member(
        client_db,
        setup,
        "fc1-full-reader@example.com",
        ["conversation.read", "booking.read", "payment.read", "room.read"],
    )
    for headers in (member, setup["headers"]):
        response, items = _results(client_db, setup, headers)
        _assert_visible(items, visible=set(TOOLS))
        assert items["get_payment_status"]["result"]["review_reason"] == REVIEW_REASON
        assert (
            items["request_booking_payment"]["result"]["destination_account_masked"]
            == DESTINATION_MASK
        )
    _grant(
        client_db,
        setup,
        membership_id,
        ["conversation.read", "booking.read", "room.read"],
    )
    response, items = _results(client_db, setup, member)
    _assert_visible(items, visible={"search_availability", "create_booking_hold"})
    assert DESTINATION_MASK not in response.text
    _grant(client_db, setup, membership_id, [])
    denied = client_db.get(setup["path"], headers=member)
    assert denied.status_code == 403, denied.text
    assert BOOKING_TOTAL not in denied.text


def test_ai_tool_results_stay_inside_their_workspace(client_db):
    setup = _ai_tool_world(client_db, "fc1-tenant@example.com")
    _, other_token = register_verify_and_login(client_db, email="fc1-other@example.com")
    before = _state(setup)
    response = client_db.get(setup["path"], headers=_auth(other_token))
    assert response.status_code == 404, response.text
    for value in (BOOKING_TOTAL, DESTINATION_MASK, REVIEW_REASON):
        assert value not in response.text
    forged = client_db.get(
        setup["path"],
        headers={**_auth(other_token), "X-Workspace-ID": str(setup["workspace_id"])},
    )
    assert forged.status_code == 403, forged.text
    assert BOOKING_TOTAL not in forged.text
    assert _state(setup) == before


def test_every_registered_tool_result_has_an_access_policy():
    # A new tool must declare who may read its result; unmapped results are
    # hidden from every caller, which would silently break the staff view.
    registry = create_ai_tool_registry()
    unmapped = [
        tool.name
        for tool in registry.list()
        if tool.output_model not in RESULT_CAPABILITIES
    ]
    assert unmapped == []
