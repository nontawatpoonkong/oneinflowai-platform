"""Knowledge upload resource limits: body size, PDF isolation, rate limits.

Covers the request-body limit enforced while the body arrives, the killable
PDF parser process (deadline, worker failure, page and character limits),
per-process and per-Workspace parse capacity, per-user and per-Workspace
upload rate limits that fail closed without Redis, authorization, and that
rejected uploads leave no document, content, or stored file behind.
"""

import asyncio
import logging
import time
from pathlib import Path

import pytest
import starlette.formparsers as formparsers
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

import app.document_parsers.isolation as isolation
import app.knowledge.upload_limits as upload_limits_module
import app.services.knowledge_document as knowledge_service_module
from app.core.body_limit import BodySizeLimitMiddleware
from app.core.config import get_settings
from app.document_parsers.exceptions import ParserWorkerFailedError, ParseTimeoutError
from app.document_parsers.isolation import ParseLimits, extract_in_subprocess
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_content import KnowledgeDocumentContent
from app.models.workspace_member import WorkspaceRole
from app.storage.local import LocalStorageProvider
from tests import parse_worker_doubles
from tests.conftest import TestSessionLocal, register_verify_and_login
from tests.test_document_extraction import _pdf
from tests.test_workspace_access import _add_member, _headers, _zero_workspace_account

UPLOAD_URL = "/api/v1/knowledge/upload"
PRIVATE_TEXT = "Private guest note 0812345678"


@pytest.fixture(autouse=True)
def knowledge_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setattr(
        knowledge_service_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(storage),
    )
    return storage


@pytest.fixture
def knowledge_settings(monkeypatch: pytest.MonkeyPatch):
    def apply(**overrides):
        settings = get_settings().model_copy(update=overrides)
        monkeypatch.setattr(knowledge_service_module, "get_settings", lambda: settings)
        monkeypatch.setattr(upload_limits_module, "get_settings", lambda: settings)
        return settings

    return apply


def _owner(client: TestClient, email: str) -> tuple[dict, dict[str, str]]:
    owner, token = register_verify_and_login(client, email=email)
    return owner, _headers(token, owner["workspace"]["id"])


def _upload(client, headers, name, content, content_type="application/pdf"):
    return client.post(
        UPLOAD_URL, headers=headers, files={"file": (name, content, content_type)}
    )


def _counts() -> tuple[int, int]:
    async def read():
        async with TestSessionLocal() as session:
            documents = await session.scalar(select(func.count(KnowledgeDocument.id)))
            contents = await session.scalar(
                select(func.count(KnowledgeDocumentContent.id))
            )
            return int(documents or 0), int(contents or 0)

    return asyncio.run(read())


def _stored_files(storage: Path) -> list[Path]:
    return [path for path in storage.rglob("*") if path.is_file()]


def _assert_safe_error(response, code: str, storage: Path) -> None:
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == code
    text = response.text
    for leak in ("Traceback", 'File "', str(storage), "site-packages", PRIVATE_TEXT):
        assert leak not in text


# --------------------------------------------------------------- accepted


def test_valid_pdf_is_parsed_in_the_isolated_process(client_db, knowledge_storage):
    _, headers = _owner(client_db, "pdf-ok@example.com")
    response = _upload(client_db, headers, "guide.pdf", _pdf("Check-in at 2pm"))
    assert response.status_code == 201, response.text
    assert response.json()["data"]["status"] == "READY"
    document_id = response.json()["data"]["id"]
    content = client_db.get(f"/api/v1/knowledge/{document_id}/content", headers=headers)
    assert "Check-in at 2pm" in content.json()["data"]["extracted_text"]
    # The parse lease is returned once the upload finishes.
    assert not any(client_db.app.state.redis.leases.values())


# ----------------------------------------------------------- request body


def test_request_body_over_the_limit_is_refused_before_the_endpoint(
    client_db, knowledge_storage
):
    _, headers = _owner(client_db, "body-limit@example.com")
    settings = get_settings()
    oversized = b"%PDF-" + b"0" * (
        settings.KNOWLEDGE_MAX_FILE_SIZE_BYTES
        + settings.KNOWLEDGE_UPLOAD_REQUEST_OVERHEAD_BYTES
    )
    response = _upload(client_db, headers, "huge.pdf", oversized)
    assert response.status_code == 413
    _assert_safe_error(response, "REQUEST_BODY_TOO_LARGE", knowledge_storage)
    assert _counts() == (0, 0)
    assert _stored_files(knowledge_storage) == []


def test_file_over_the_limit_inside_an_allowed_body_is_refused(
    client_db, knowledge_storage, knowledge_settings
):
    _, headers = _owner(client_db, "file-limit@example.com")
    knowledge_settings(KNOWLEDGE_MAX_FILE_SIZE_BYTES=1024)
    response = _upload(client_db, headers, "big.pdf", b"%PDF-" + b"0" * 2048)
    assert response.status_code == 413
    _assert_safe_error(response, "KNOWLEDGE_FILE_TOO_LARGE", knowledge_storage)
    assert _counts() == (0, 0)
    assert _stored_files(knowledge_storage) == []


def test_malformed_multipart_is_a_client_error(client_db, knowledge_storage):
    _, headers = _owner(client_db, "multipart@example.com")
    response = client_db.post(
        UPLOAD_URL,
        headers={**headers, "Content-Type": "multipart/form-data; boundary=zzz"},
        content=b"--zzz\r\nContent-Disposition: form-data; name=\r\n\r\nbroken",
    )
    assert response.status_code in {400, 422}
    assert "Traceback" not in response.text
    assert _counts() == (0, 0)


def _limited_app(limit: int, reached: list[int]) -> FastAPI:
    app = FastAPI()

    @app.post("/upload")
    async def upload(file: UploadFile) -> dict:
        reached.append(1)
        return {"size": len(await file.read())}

    app.add_middleware(BodySizeLimitMiddleware, limits={("POST", "/upload"): limit})
    return app


def test_chunked_body_without_length_is_cut_off_and_temp_files_are_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    created: list = []

    class RecordingSpool(formparsers.SpooledTemporaryFile):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", RecordingSpool)
    # Roll every file part to a real temporary file on disk.
    monkeypatch.setattr(formparsers.MultiPartParser, "spool_max_size", 16)
    reached: list[int] = []
    app = _limited_app(4096, reached)
    # Feed the body the way a server does for chunked transfer encoding:
    # many messages and no Content-Length header.
    header = (
        b'--b\r\nContent-Disposition: form-data; name="file"; '
        b'filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
    )
    chunks = [header] + [b"x" * 1024] * 64
    sent: list[dict] = []

    async def receive():
        body = chunks.pop(0) if chunks else b""
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-type", b"multipart/form-data; boundary=b")],
        "client": ("testclient", 1),
        "server": ("testserver", 80),
        "state": {},
    }
    asyncio.run(app(scope, receive, send))

    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 413
    body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    assert b"REQUEST_BODY_TOO_LARGE" in body
    assert reached == []
    assert chunks, "the rest of the body was never read"
    assert created, "the multipart parser should have opened a temporary file"
    assert all(spool.closed for spool in created)


def test_body_within_the_limit_still_reaches_the_endpoint():
    reached: list[int] = []
    client = TestClient(_limited_app(4096, reached))
    response = client.post(
        "/upload", files={"file": ("a.pdf", b"%PDF-small", "application/pdf")}
    )
    assert response.status_code == 200
    assert response.json() == {"size": len(b"%PDF-small")}
    assert reached == [1]


# --------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    ("name", "content", "code", "status"),
    [
        ("fake.pdf", b"MZ executable", "INVALID_KNOWLEDGE_FILE", 400),
        (
            "broken.pdf",
            b"%PDF-1.7\n" + b"\x00garbage" * 50,
            "KNOWLEDGE_EXTRACTION_FAILED",
            422,
        ),
        (
            "locked.pdf",
            _pdf(PRIVATE_TEXT, encrypted=True),
            "KNOWLEDGE_EXTRACTION_FAILED",
            422,
        ),
    ],
    ids=["bad-signature", "corrupted", "encrypted"],
)
def test_invalid_pdfs_are_refused_without_content(
    client_db, knowledge_storage, caplog, name, content, code, status
):
    _, headers = _owner(client_db, f"{name.split('.')[0]}@example.com")
    with caplog.at_level(logging.DEBUG):
        response = _upload(client_db, headers, name, content)
    assert response.status_code == status
    _assert_safe_error(response, code, knowledge_storage)
    documents, contents = _counts()
    assert contents == 0
    assert documents == (0 if status == 400 else 1)
    assert PRIVATE_TEXT not in caplog.text


def test_pdf_over_the_page_limit_fails_before_text_is_kept(
    client_db, knowledge_storage, knowledge_settings, caplog
):
    _, headers = _owner(client_db, "pages@example.com")
    knowledge_settings(KNOWLEDGE_MAX_PDF_PAGES=2)
    with caplog.at_level(logging.WARNING):
        response = _upload(client_db, headers, "long.pdf", _pdf("one", "two", "three"))
    assert response.status_code == 422
    _assert_safe_error(response, "KNOWLEDGE_EXTRACTION_FAILED", knowledge_storage)
    assert _counts() == (1, 0)
    reasons = [getattr(record, "reason", None) for record in caplog.records]
    assert "PageLimitExceededError" in reasons


def test_pdf_text_over_the_character_limit_stops_during_extraction(
    client_db, knowledge_storage, knowledge_settings, caplog
):
    _, headers = _owner(client_db, "characters@example.com")
    knowledge_settings(KNOWLEDGE_MAX_EXTRACTED_CHARACTERS=10)
    with caplog.at_level(logging.WARNING):
        response = _upload(
            client_db, headers, "wordy.pdf", _pdf("a" * 40, "b" * 40, "c" * 40)
        )
    assert response.status_code == 422
    assert _counts() == (1, 0)
    reasons = [getattr(record, "reason", None) for record in caplog.records]
    assert "ExtractionLimitExceededError" in reasons


def _limits(timeout: float) -> ParseLimits:
    return ParseLimits(
        maximum_characters=1000,
        maximum_pages=10,
        timeout_seconds=timeout,
        memory_limit_bytes=512 * 1024 * 1024,
    )


def test_parse_deadline_kills_the_parser_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        isolation, "_child_main", parse_worker_doubles.heartbeat_forever
    )
    marker = tmp_path / "heartbeat"
    started = time.monotonic()
    with pytest.raises(ParseTimeoutError):
        extract_in_subprocess(mime_type=str(marker), data=b"", limits=_limits(3.0))
    assert time.monotonic() - started < 3.0 + 10
    assert marker.exists(), "the child should have been running before the deadline"
    beat = marker.read_text()
    time.sleep(0.5)
    assert marker.read_text() == beat, "the child kept running after the deadline"


def test_parser_process_that_dies_is_reported_as_a_worker_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(isolation, "_child_main", parse_worker_doubles.exit_abruptly)
    with pytest.raises(ParserWorkerFailedError):
        extract_in_subprocess(
            mime_type="application/pdf", data=b"%PDF-", limits=_limits(30.0)
        )


def test_upload_whose_parse_times_out_is_marked_failed(
    client_db, knowledge_storage, knowledge_settings, monkeypatch, caplog
):
    _, headers = _owner(client_db, "timeout@example.com")
    knowledge_settings(KNOWLEDGE_PARSE_TIMEOUT_SECONDS=0.01)
    with caplog.at_level(logging.WARNING):
        response = _upload(client_db, headers, "slow.pdf", _pdf("slow"))
    assert response.status_code == 422
    _assert_safe_error(response, "KNOWLEDGE_EXTRACTION_FAILED", knowledge_storage)
    assert _counts() == (1, 0)
    reasons = [getattr(record, "reason", None) for record in caplog.records]
    assert "ParseTimeoutError" in reasons


# ------------------------------------------------------ capacity and rates


def test_busy_process_refuses_new_uploads_before_reading_them(
    client_db, knowledge_storage, knowledge_settings
):
    _, headers = _owner(client_db, "busy@example.com")
    knowledge_settings(KNOWLEDGE_MAX_CONCURRENT_PARSES=1)
    slots = knowledge_service_module._local_parse_slots(1)
    assert slots.acquire(blocking=False)
    try:
        refused = _upload(client_db, headers, "a.pdf", _pdf("a"))
    finally:
        slots.release()
    assert refused.status_code == 503
    assert refused.headers["Retry-After"]
    _assert_safe_error(refused, "KNOWLEDGE_UPLOAD_BUSY", knowledge_storage)
    assert _counts() == (0, 0)
    assert _upload(client_db, headers, "a.pdf", _pdf("a")).status_code == 201


def test_workspace_parse_leases_cap_concurrent_uploads(
    client_db, knowledge_storage, knowledge_settings
):
    owner, headers = _owner(client_db, "leases@example.com")
    knowledge_settings(KNOWLEDGE_MAX_CONCURRENT_PARSES_PER_WORKSPACE=2)
    held_until = time.time() + 600
    key = f"knowledge-parse-leases:{owner['workspace']['id']}"
    client_db.app.state.redis.leases[key] = {"one": held_until, "two": held_until}
    refused = _upload(client_db, headers, "a.pdf", _pdf("a"))
    assert refused.status_code == 429
    _assert_safe_error(refused, "KNOWLEDGE_UPLOAD_RATE_LIMITED", knowledge_storage)
    assert _counts() == (0, 0)
    # Expired leases (a crashed worker) stop counting on their own.
    client_db.app.state.redis.leases[key] = {"one": time.time() - 1}
    assert _upload(client_db, headers, "a.pdf", _pdf("a")).status_code == 201


def test_user_rate_limit_follows_the_user_across_workspaces(
    client_db, knowledge_storage, knowledge_settings
):
    owner, headers = _owner(client_db, "rate-user@example.com")
    other, _ = register_verify_and_login(client_db, email="rate-other@example.com")
    _add_member(other["workspace"]["id"], owner["user"]["id"], WorkspaceRole.ADMIN)
    knowledge_settings(
        KNOWLEDGE_UPLOAD_RATE_LIMIT_PER_USER=2,
        KNOWLEDGE_UPLOAD_RATE_LIMIT_PER_WORKSPACE=100,
    )
    token = headers["Authorization"]
    first = {"Authorization": token, "X-Workspace-ID": owner["workspace"]["id"]}
    second = {"Authorization": token, "X-Workspace-ID": other["workspace"]["id"]}
    assert _upload(client_db, first, "a.txt", b"a", "text/plain").status_code == 201
    assert _upload(client_db, second, "b.txt", b"b", "text/plain").status_code == 201
    refused = _upload(client_db, second, "c.txt", b"c", "text/plain")
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) >= 1
    _assert_safe_error(refused, "KNOWLEDGE_UPLOAD_RATE_LIMITED", knowledge_storage)
    assert _counts()[0] == 2


def test_workspace_rate_limit_applies_to_every_member(
    client_db, knowledge_storage, knowledge_settings
):
    _, headers = _owner(client_db, "rate-workspace@example.com")
    knowledge_settings(
        KNOWLEDGE_UPLOAD_RATE_LIMIT_PER_USER=100,
        KNOWLEDGE_UPLOAD_RATE_LIMIT_PER_WORKSPACE=1,
    )
    assert _upload(client_db, headers, "a.txt", b"a", "text/plain").status_code == 201
    refused = _upload(client_db, headers, "b.txt", b"b", "text/plain")
    assert refused.status_code == 429
    assert _counts()[0] == 1


def test_uploads_are_refused_when_the_limiter_is_unavailable(
    client_db, knowledge_storage, monkeypatch
):
    _, headers = _owner(client_db, "redis-down@example.com")

    async def unavailable(*args, **kwargs):
        raise RedisConnectionError("redis host detail")

    monkeypatch.setattr(client_db.app.state.redis, "eval", unavailable)
    response = _upload(client_db, headers, "a.pdf", _pdf("a"))
    assert response.status_code == 503
    _assert_safe_error(response, "KNOWLEDGE_UPLOAD_UNAVAILABLE", knowledge_storage)
    assert "redis host detail" not in response.text
    assert _counts() == (0, 0)


# ---------------------------------------------------------- authorization


def test_member_without_knowledge_manage_cannot_upload(client_db, knowledge_storage):
    owner, owner_headers = _owner(client_db, "manage-owner@example.com")
    user, token = _zero_workspace_account(client_db, "manage-reader@example.com")
    membership_id = _add_member(
        owner["workspace"]["id"], user["id"], WorkspaceRole.MEMBER
    )
    granted = client_db.put(
        f"/api/v1/workspaces/{owner['workspace']['id']}/members/{membership_id}/capabilities",
        headers=owner_headers,
        json={"capabilities": ["knowledge.read"]},
    )
    assert granted.status_code == 200, granted.text
    response = _upload(
        client_db, _headers(token, owner["workspace"]["id"]), "a.pdf", _pdf("a")
    )
    assert response.status_code == 403
    assert _counts() == (0, 0)
    # Refused by authorization before any upload rate counter is touched.
    assert not [key for key in client_db.app.state.redis.values if "knowledge" in key]


def test_other_workspace_cannot_receive_uploads(client_db, knowledge_storage):
    owner, _ = _owner(client_db, "victim@example.com")
    _, attacker = _owner(client_db, "attacker@example.com")
    response = _upload(
        client_db,
        {**attacker, "X-Workspace-ID": owner["workspace"]["id"]},
        "a.pdf",
        _pdf("a"),
    )
    assert response.status_code in {403, 404}
    assert _counts() == (0, 0)
