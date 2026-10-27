"""Seed the browser E2E Workspace (not part of the regular suite).

Run only against a dedicated ``*_e2e`` database; the schema is recreated.
frontend/e2e/global-setup.ts runs it before the browser tests with
TEST_DATABASE_URL pointing at ``.../oneflowai_e2e`` and E2E_SEED_OUT set.

The file name does not match ``test_*.py``, so the full suite never runs it.
Every account uses the test-only password from the test helpers.
"""

import json
import os
from pathlib import Path

import pytest

from app.models.workspace_member import WorkspaceRole
from tests.conftest import TEST_DATABASE_URL, register_verify_and_login
from tests.test_crm import _customer
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

PASSWORD = "supersecret123"
GUEST_PHONE = "+66899990001"
MEMBERS = {
    "member_none": [],
    "member_read": ["action.read"],
    "member_operate": ["action.operate"],
    "member_both": ["action.read", "action.operate"],
}


def test_seed_e2e_world(client_db):
    if not TEST_DATABASE_URL.rsplit("/", 1)[-1].endswith("_e2e"):
        pytest.skip("E2E seed runs only against a dedicated *_e2e database")
    owner, token = register_verify_and_login(
        client_db, email="e2e-owner@example.com", full_name="E2E Owner"
    )
    workspace_id = owner["workspace"]["id"]
    owner_headers = _headers(token)
    definition = client_db.post(
        "/api/v1/actions/definitions",
        headers=owner_headers,
        json={
            "key": "guest_callback",
            "name": "Guest callback",
            "required_fields": [
                {
                    "key": "guest_phone",
                    "label": "Guest phone",
                    "type": "string",
                    "required": True,
                }
            ],
        },
    )
    assert definition.status_code == 201, definition.text
    customer = _customer(client_db, token, "E2E Guest")
    action = client_db.post(
        "/api/v1/actions",
        headers=owner_headers,
        json={
            "action_definition_id": definition.json()["data"]["id"],
            "customer_id": customer["id"],
            "payload": {"guest_phone": GUEST_PHONE},
        },
    )
    assert action.status_code == 201, action.text

    accounts = {"owner": "e2e-owner@example.com"}
    admin, _ = _zero_workspace_account(client_db, "e2e-admin@example.com")
    _add_member(workspace_id, admin["id"], WorkspaceRole.ADMIN)
    accounts["admin"] = "e2e-admin@example.com"
    for name, capabilities in MEMBERS.items():
        email = f"e2e-{name.replace('_', '-')}@example.com"
        user, _ = _zero_workspace_account(client_db, email)
        membership_id = _add_member(workspace_id, user["id"], WorkspaceRole.MEMBER)
        granted = client_db.put(
            f"/api/v1/workspaces/{workspace_id}/members/{membership_id}/capabilities",
            headers=owner_headers,
            json={"capabilities": capabilities},
        )
        assert granted.status_code == 200, granted.text
        accounts[name] = email

    out = os.environ.get("E2E_SEED_OUT")
    if out:
        Path(out).write_text(
            json.dumps(
                {
                    "password": PASSWORD,
                    "accounts": accounts,
                    "workspace_id": workspace_id,
                    "action_id": action.json()["data"]["id"],
                    "guest_phone": GUEST_PHONE,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
