"""Knowledge document API and storage tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.knowledge_document as knowledge_service_module
from app.core.config import Settings
from app.storage.local import LocalStorageProvider
from tests.conftest import FakeEmailProvider, register_verify_and_login

BASE_URL = "/api/v1/knowledge"


@pytest.fixture
def knowledge_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    return tmp_path


def _auth(
    client: TestClient,
    fake_email_provider: FakeEmailProvider,
    email: str = "knowledge@example.com",
) -> dict[str, str]:
    _, token = register_verify_and_login(client, email=email)
    return {"Authorization": f"Bearer {token}"}


def _upload(
    client: TestClient,
    headers: dict[str, str],
    *,
    filename: str = "guide.txt",
    content: bytes = b"OneInFlow knowledge",
    content_type: str = "text/plain",
):
    return client.post(
        f"{BASE_URL}/upload",
        headers=headers,
        files={"file": (filename, content, content_type)},
    )


def test_upload_success_stores_file_and_hides_storage_key(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    knowledge_storage: Path,
) -> None:
    response = _upload(client_db, _auth(client_db, fake_email_provider))
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "guide"
    assert data["status"] == "READY"
    assert data["file_size"] == len(b"OneInFlow knowledge")
    assert "storage_key" not in data
    assert len([path for path in knowledge_storage.rglob("*") if path.is_file()]) == 1


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("malware.exe", "application/octet-stream"), ("guide.pdf", "text/plain")],
)
def test_invalid_extension_or_mime_is_rejected(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    knowledge_storage: Path,
    filename: str,
    content_type: str,
) -> None:
    response = _upload(
        client_db,
        _auth(client_db, fake_email_provider),
        filename=filename,
        content_type=content_type,
    )
    assert response.status_code == 400
    assert not list(knowledge_storage.rglob("*.*"))


def test_oversize_file_is_rejected(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    knowledge_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, KNOWLEDGE_MAX_FILE_SIZE_BYTES=4)
    monkeypatch.setattr(knowledge_service_module, "get_settings", lambda: settings)
    response = _upload(
        client_db,
        _auth(client_db, fake_email_provider),
        content=b"12345",
    )
    assert response.status_code == 413
    assert not list(knowledge_storage.rglob("*.*"))


def test_list_detail_and_missing_document(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    knowledge_storage: Path,
) -> None:
    headers = _auth(client_db, fake_email_provider)
    uploaded = _upload(client_db, headers).json()["data"]
    listing = client_db.get(BASE_URL, headers=headers)
    detail = client_db.get(f"{BASE_URL}/{uploaded['id']}", headers=headers)
    missing = client_db.get(
        f"{BASE_URL}/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert listing.status_code == detail.status_code == 200
    assert listing.json()["data"]["items"][0]["id"] == uploaded["id"]
    assert listing.json()["data"]["total"] == 1
    assert detail.json()["data"]["id"] == uploaded["id"]
    assert missing.status_code == 404


def test_workspace_isolation(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    knowledge_storage: Path,
) -> None:
    first_headers = _auth(client_db, fake_email_provider, "first@example.com")
    document = _upload(client_db, first_headers).json()["data"]
    second_headers = _auth(client_db, fake_email_provider, "second@example.com")
    assert client_db.get(BASE_URL, headers=second_headers).json()["data"]["total"] == 0
    isolated_detail = client_db.get(
        f"{BASE_URL}/{document['id']}", headers=second_headers
    )
    assert isolated_detail.status_code == 404


def test_delete_soft_deletes_metadata_and_removes_file(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    knowledge_storage: Path,
) -> None:
    headers = _auth(client_db, fake_email_provider)
    document = _upload(client_db, headers).json()["data"]
    response = client_db.delete(f"{BASE_URL}/{document['id']}", headers=headers)
    assert response.status_code == 200
    deleted_detail = client_db.get(f"{BASE_URL}/{document['id']}", headers=headers)
    assert deleted_detail.status_code == 404
    assert not [path for path in knowledge_storage.rglob("*") if path.is_file()]


def test_duplicate_filenames_receive_distinct_storage_keys(
    client_db: TestClient,
    fake_email_provider: FakeEmailProvider,
    knowledge_storage: Path,
) -> None:
    headers = _auth(client_db, fake_email_provider)
    first = _upload(client_db, headers)
    second = _upload(client_db, headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] != second.json()["data"]["id"]
    assert len([path for path in knowledge_storage.rglob("*") if path.is_file()]) == 2
