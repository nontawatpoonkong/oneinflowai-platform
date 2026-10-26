"""Platform campaign authoring requires an ACTIVE Workspace; exposure-reducing
lifecycle operations stay available while a Workspace is SUSPENDED."""

import asyncio
import uuid

from sqlalchemy import func, select

from app.models.audit import WorkspaceAuditEvent
from app.models.promotion import Promotion, PromotionCode
from tests.conftest import TestSessionLocal
from tests.test_booking import _setup
from tests.test_campaign_operations import P, _platform_campaign
from tests.test_platform_admin import _confirmed, _platform_admin
from tests.test_promotions import _promotion

RULE = {"name": "Rule", "discount_type": "PERCENTAGE", "discount_value": "10"}


def _set_workspace(client, admin, workspace_id, action):
    response = client.post(
        f"/api/v1/platform/workspaces/{workspace_id}/{action}",
        headers=admin,
        json=_confirmed(),
    )
    assert response.status_code == 200, response.text


def _counts(workspace_id):
    async def read():
        async with TestSessionLocal() as session:

            async def count(model, *filters):
                return await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.workspace_id == workspace_id, *filters)
                )

            return (
                await count(Promotion),
                await count(PromotionCode),
                await count(
                    WorkspaceAuditEvent,
                    WorkspaceAuditEvent.actor_type == "PLATFORM_ADMIN",
                ),
            )

    return asyncio.run(read())


def _assert_not_active(response):
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "PLATFORM_CAMPAIGN_OPERATION_INVALID"
    assert error["details"]["reason_code"] == "WORKSPACE_NOT_ACTIVE"


def test_authoring_is_rejected_while_workspace_suspended(client_db):
    user, *_ = _setup(client_db)
    workspace_id = user["workspace"]["id"]
    _, admin = _platform_admin(client_db)
    detail = _platform_campaign(client_db, admin, workspace_id)
    campaign_id = detail["campaign"]["id"]
    rule = client_db.post(
        f"{P}/campaigns/{campaign_id}/rules", headers=admin, json=RULE | _confirmed()
    )
    assert rule.status_code == 201, rule.text
    rule_id = rule.json()["data"]["rules"][0]["id"]

    _set_workspace(client_db, admin, workspace_id, "suspend")
    before = _counts(uuid.UUID(workspace_id))
    # The console is told authoring is unavailable; reductions remain.
    suspended_detail = client_db.get(f"{P}/campaigns/{campaign_id}", headers=admin)
    data = suspended_detail.json()["data"]
    assert data["allowed_operations"] == ["archive"]
    assert data["editable_fields"] == []

    _assert_not_active(
        client_db.post(
            f"{P}/campaigns/{campaign_id}/rules",
            headers=admin,
            json=RULE | _confirmed(),
        )
    )
    _assert_not_active(
        client_db.post(
            f"{P}/campaigns/{campaign_id}/codes",
            headers=admin,
            json={"promotion_id": rule_id, "code": "PAUSED1"} | _confirmed(),
        )
    )
    _assert_not_active(
        client_db.patch(
            f"{P}/campaigns/{campaign_id}",
            headers=admin,
            json={"name": "Renamed"} | _confirmed(),
        )
    )
    # Nothing was written: no rule, no code, no platform audit event.
    assert _counts(uuid.UUID(workspace_id)) == before
    unchanged = client_db.get(f"{P}/campaigns/{campaign_id}", headers=admin)
    assert unchanged.json()["data"]["campaign"]["name"] == "Platform Spring"

    # Reactivation restores authoring.
    _set_workspace(client_db, admin, workspace_id, "reactivate")
    code = client_db.post(
        f"{P}/campaigns/{campaign_id}/codes",
        headers=admin,
        json={"promotion_id": rule_id, "code": "BACK1"} | _confirmed(),
    )
    assert code.status_code == 201, code.text
    renamed = client_db.patch(
        f"{P}/campaigns/{campaign_id}",
        headers=admin,
        json={"name": "Renamed"} | _confirmed(),
    )
    assert renamed.status_code == 200, renamed.text
    restored = client_db.get(f"{P}/campaigns/{campaign_id}", headers=admin)
    assert {"add_rule", "add_code"} <= set(
        restored.json()["data"]["allowed_operations"]
    )


def test_exposure_reducing_operations_stay_available_while_suspended(client_db):
    user, token, prop, room, plan = _setup(client_db)
    workspace_id = user["workspace"]["id"]
    campaign, _, code = _promotion(client_db, token, prop, room, plan)
    _, admin = _platform_admin(client_db)
    _set_workspace(client_db, admin, workspace_id, "suspend")

    disabled = client_db.post(
        f"{P}/codes/{code['id']}/disable", headers=admin, json=_confirmed()
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == "DISABLED"
    for verb, status in (
        ("pause", "PAUSED"),
        ("expire", "EXPIRED"),
        ("archive", "ARCHIVED"),
    ):
        response = client_db.post(
            f"{P}/campaigns/{campaign['id']}/{verb}", headers=admin, json=_confirmed()
        )
        assert response.status_code == 200, (verb, response.text)
        assert response.json()["data"]["status"] == status
    archived_code = client_db.post(
        f"{P}/codes/{code['id']}/archive", headers=admin, json=_confirmed()
    )
    assert archived_code.status_code == 200, archived_code.text
