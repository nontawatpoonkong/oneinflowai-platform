"""F-C1 transcript: AI tool results never travel through message metadata.

(a) New assistant messages store the AI tool action id, not its result; the
    structured result lives only on the AI tool action, whose staff view is
    gated by the result's own capability.
(b) Rows stored before (a) still carry ``ai_tool_result``; staff message
    responses withhold it unless the caller may read that tool's result.
"""

import asyncio
import uuid

from sqlalchemy import select

from app.models.ai_tool import AIToolAction
from app.models.message import Message
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_ai_action_orchestration import _send_tool
from tests.test_ai_tool_result_visibility import (
    DESTINATION_MASK,
    REVIEW_REASON,
    _ai_tool_world,
    _grant,
    _member,
)
from tests.test_hotel import _auth

PROTECTED_TOOLS = {
    "request_booking_payment",
    "get_payment_status",
    "get_booking_status",
}


def _tool_messages(setup):
    async def read():
        async with TestSessionLocal() as session:
            rows = await session.scalars(
                select(Message)
                .where(
                    Message.conversation_id
                    == uuid.UUID(setup["webchat"]["conversation_id"])
                )
                .order_by(Message.created_at, Message.id)
            )
            return [
                (row.id, dict(row.extra_metadata))
                for row in rows
                if (row.extra_metadata or {}).get("ai_tool_action_id")
            ]

    return asyncio.run(read())


def _restore_legacy_results(setup, *, action_id=None):
    """Write results back into metadata, as rows stored before (a) look."""

    async def write():
        async with TestSessionLocal() as session:
            rows = await session.scalars(
                select(Message).where(
                    Message.conversation_id
                    == uuid.UUID(setup["webchat"]["conversation_id"])
                )
            )
            for row in rows:
                metadata = dict(row.extra_metadata or {})
                tool_action_id = metadata.get("ai_tool_action_id")
                if not tool_action_id:
                    continue
                action = await session.get(AIToolAction, uuid.UUID(tool_action_id))
                if action is None or action.result is None:
                    continue
                metadata["ai_tool_result"] = action.result
                if action_id is not None:
                    metadata["ai_tool_action_id"] = action_id
                row.extra_metadata = metadata
            await session.commit()

    asyncio.run(write())


def _messages(client, setup, headers):
    response = client.get(
        f"/api/v1/conversations/{setup['webchat']['conversation_id']}/messages"
        "?page_size=100",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    tool_items = [
        item
        for item in response.json()["data"]["items"]
        if item["metadata"].get("ai_tool_action_id")
    ]
    assert tool_items
    return response, {item["metadata"]["ai_tool_name"]: item for item in tool_items}


def test_new_assistant_messages_do_not_store_tool_results(client_db):
    setup = _ai_tool_world(client_db, "tr-new@example.com")
    stored = _tool_messages(setup)
    assert {metadata["ai_tool_name"] for _, metadata in stored} >= PROTECTED_TOOLS
    for _, metadata in stored:
        assert metadata.get("ai_tool_result") is None, metadata["ai_tool_name"]
        assert metadata["ai_tool_action_id"]

    # Replays rebuild the result from the AI tool action, so the visitor still
    # gets it back even though the message no longer stores it.
    replay = _send_tool(
        client_db, setup, "fc1-payment-status", "action:ai_tool:get_payment_status:1 {}"
    )
    assert replay.status_code == 201, replay.text
    result = replay.json()["data"]["assistant"]["ai_tool_action"]["result"]
    assert result["review_reason"] == REVIEW_REASON


def test_stored_tool_results_follow_the_callers_capabilities(client_db):
    setup = _ai_tool_world(client_db, "tr-legacy@example.com")
    _restore_legacy_results(setup)
    conversation_only, membership_id = _member(
        client_db, setup, "tr-conversation@example.com", ["conversation.read"]
    )
    response, items = _messages(client_db, setup, conversation_only)
    for name in PROTECTED_TOOLS:
        assert items[name]["metadata"]["ai_tool_result"] is None, name
        assert items[name]["metadata"]["ai_tool_result_visible"] is False, name
    # The guest-facing message text is unchanged; values that only the
    # structured result carried are gone.
    for value in (DESTINATION_MASK, REVIEW_REASON):
        assert value not in response.text, value

    _grant(
        client_db,
        setup,
        membership_id,
        ["conversation.read", "booking.read", "payment.read", "room.read"],
    )
    response, items = _messages(client_db, setup, conversation_only)
    assert (
        items["get_payment_status"]["metadata"]["ai_tool_result"]["review_reason"]
        == REVIEW_REASON
    )
    assert items["get_payment_status"]["metadata"].get("ai_tool_result_visible", True)
    owner_response, owner_items = _messages(client_db, setup, setup["headers"])
    assert DESTINATION_MASK in owner_response.text

    _grant(client_db, setup, membership_id, ["conversation.read", "booking.read"])
    response, items = _messages(client_db, setup, conversation_only)
    assert items["get_payment_status"]["metadata"]["ai_tool_result"] is None
    assert items["create_booking_hold"]["metadata"]["ai_tool_result"]


def test_stored_results_with_unknown_or_foreign_tool_ids_stay_hidden(client_db):
    setup = _ai_tool_world(client_db, "tr-foreign@example.com")
    other = _ai_tool_world(client_db, "tr-foreign-other@example.com")

    async def foreign_action_id():
        async with TestSessionLocal() as session:
            return str(
                await session.scalar(
                    select(AIToolAction.id).where(
                        AIToolAction.workspace_id == other["workspace_id"],
                        AIToolAction.tool_name == "get_payment_status",
                    )
                )
            )

    # Every stored result now points at another Workspace's AI tool action.
    _restore_legacy_results(setup, action_id=asyncio.run(foreign_action_id()))
    response, items = _messages(client_db, setup, setup["headers"])
    for item in items.values():
        assert item["metadata"]["ai_tool_result"] is None
        assert item["metadata"]["ai_tool_result_visible"] is False
    assert DESTINATION_MASK not in response.text

    _, outsider_token = register_verify_and_login(
        client_db, email="tr-outsider@example.com"
    )
    outsider = client_db.get(
        f"/api/v1/conversations/{setup['webchat']['conversation_id']}/messages",
        headers=_auth(outsider_token),
    )
    assert outsider.status_code == 404, outsider.text
    assert REVIEW_REASON not in outsider.text
