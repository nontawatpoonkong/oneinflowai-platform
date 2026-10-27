"""M5: knowledge routes follow knowledge.read and knowledge.manage.

Runtime evidence for the route inventory: members without knowledge.read get
no document metadata, content or chunks; knowledge.read never implies
upload, re-chunk, index or delete; other Workspaces see nothing.
"""

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

import app.services.knowledge_document as knowledge_service_module
from app.models.knowledge_document import KnowledgeDocument
from app.models.workspace_member import WorkspaceRole
from app.storage.local import LocalStorageProvider
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_workspace_access import (
    _add_member,
    _headers,
    _zero_workspace_account,
)

BASE_URL = "/api/v1/knowledge"
SECRET_TEXT = "Staff wifi password is OneInFlow-2026"


@pytest.fixture(autouse=True)
def knowledge_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    return tmp_path


def _world(client, email):
    owner, token = register_verify_and_login(client, email=email)
    headers = _headers(token)
    uploaded = client.post(
        f"{BASE_URL}/upload",
        headers=headers,
        files={"file": ("handbook.txt", SECRET_TEXT.encode(), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    return {
        "workspace_id": owner["workspace"]["id"],
        "token": token,
        "headers": headers,
        "document": uploaded.json()["data"]["id"],
    }


def _member(client, world, email, capabilities):
    user, token = _zero_workspace_account(client, email)
    membership_id = _add_member(world["workspace_id"], user["id"], WorkspaceRole.MEMBER)
    granted = client.put(
        f"/api/v1/workspaces/{world['workspace_id']}/members/{membership_id}/capabilities",
        headers=_headers(world["token"]),
        json={"capabilities": capabilities},
    )
    assert granted.status_code == 200, granted.text
    return _headers(token, world["workspace_id"])


def _documents(world):
    async def read():
        async with TestSessionLocal() as session:
            rows = await session.execute(
                select(
                    KnowledgeDocument.id,
                    KnowledgeDocument.status,
                    KnowledgeDocument.index_status,
                    KnowledgeDocument.updated_at,
                ).where(
                    KnowledgeDocument.workspace_id == uuid.UUID(world["workspace_id"])
                )
            )
            return sorted(tuple(row) for row in rows.all())

    return asyncio.run(read())


def _reads(world):
    document = world["document"]
    return [
        ("get", BASE_URL, None),
        ("get", f"{BASE_URL}/{document}", None),
        ("get", f"{BASE_URL}/{document}/content", None),
        ("get", f"{BASE_URL}/{document}/chunks", None),
        ("post", f"{BASE_URL}/search", {"query": "wifi"}),
    ]


def _changes(world):
    document = world["document"]
    return [
        ("post", f"{BASE_URL}/{document}/rechunk", None),
        ("post", f"{BASE_URL}/{document}/index", None),
        ("delete", f"{BASE_URL}/{document}", None),
    ]


def _send(client, method, path, body, headers):
    if body is None:
        return getattr(client, method)(path, headers=headers)
    return getattr(client, method)(path, headers=headers, json=body)


def _assert_denied(client, headers, requests, capability):
    for method, path, body in requests:
        response = _send(client, method, path, body, headers)
        assert response.status_code == 403, (path, response.text)
        assert capability in response.json()["message"], path
        assert SECRET_TEXT not in response.text
        assert "handbook.txt" not in response.text


def test_member_without_knowledge_read_sees_nothing(client_db):
    world = _world(client_db, "m5-none-owner@example.com")
    member = _member(client_db, world, "m5-none@example.com", [])
    before = _documents(world)
    _assert_denied(client_db, member, _reads(world), "knowledge.read")
    _assert_denied(client_db, member, _changes(world), "knowledge.manage")
    upload = client_db.post(
        f"{BASE_URL}/upload",
        headers=member,
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert upload.status_code == 403, upload.text
    assert _documents(world) == before


def test_knowledge_reader_reads_but_cannot_manage(client_db):
    world = _world(client_db, "m5-read-owner@example.com")
    member = _member(client_db, world, "m5-reader@example.com", ["knowledge.read"])
    before = _documents(world)
    content = client_db.get(f"{BASE_URL}/{world['document']}/content", headers=member)
    assert content.status_code == 200, content.text
    assert SECRET_TEXT in content.text
    _assert_denied(client_db, member, _changes(world), "knowledge.manage")
    assert _documents(world) == before


def test_knowledge_stays_inside_its_workspace(client_db):
    world = _world(client_db, "m5-tenant-a@example.com")
    _, other_token = register_verify_and_login(
        client_db, email="m5-tenant-b@example.com"
    )
    other = _headers(other_token)
    for method, path, body in _reads(world)[1:4] + _changes(world):
        response = _send(client_db, method, path, body, other)
        assert response.status_code == 404, (path, response.text)
        assert SECRET_TEXT not in response.text
    listing = client_db.get(BASE_URL, headers=other)
    assert world["document"] not in listing.text
    forged = client_db.get(
        f"{BASE_URL}/{world['document']}/content",
        headers={**other, "X-Workspace-ID": world["workspace_id"]},
    )
    assert forged.status_code == 403, forged.text
    assert SECRET_TEXT not in forged.text
