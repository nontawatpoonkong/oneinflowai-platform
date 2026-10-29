"""Request body limits on every route, and pre-authorization of uploads.

The upload routes for payment evidence and room images, the public channel
webhooks, and every other route are bounded while the body arrives. Upload
routes also check the bearer token from the headers before any body byte is
read, with the same outcome `get_current_user` would give.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import app.services.payment as payment_module
from app.core.body_limit import BodyLimitRule, BodySizeLimitMiddleware
from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import app as main_app
from app.services.hotel_catalog import ROOM_IMAGE_MAX_BYTES
from app.storage.local import LocalStorageProvider
from tests.conftest import register_verify_and_login

API = "/api/v1"
JPEG = b"\xff\xd8\xff"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_too_large(response) -> None:
    assert response.status_code == 413
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "REQUEST_BODY_TOO_LARGE"
    assert "Traceback" not in response.text


@pytest.fixture
def evidence_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        payment_module,
        "create_storage_provider",
        lambda settings: LocalStorageProvider(tmp_path),
    )
    return tmp_path


# ------------------------------------------------------- route matching


def _echo_app(**middleware) -> FastAPI:
    app = FastAPI()

    @app.post("/items/{item_id}/files")
    @app.post("/items/{item_id}/files/extra")
    @app.post("/other")
    async def echo(request: Request) -> dict:
        return {"size": len(await request.body())}

    app.add_middleware(BodySizeLimitMiddleware, **middleware)
    return app


def test_route_templates_match_one_segment_per_placeholder():
    client = TestClient(
        _echo_app(
            default_max_bytes=10,
            rules=[BodyLimitRule("POST", "/items/{item_id}/files", 100)],
        )
    )
    assert client.post("/items/abc/files", content=b"x" * 100).status_code == 200
    _assert_too_large(client.post("/items/abc/files", content=b"x" * 101))
    # A longer path, or a slash inside the placeholder, falls to the default.
    _assert_too_large(client.post("/items/abc/files/extra", content=b"x" * 50))
    _assert_too_large(client.post("/items/a/b/files", content=b"x" * 50))
    assert client.post("/other", content=b"x" * 10).status_code == 200
    _assert_too_large(client.post("/other", content=b"x" * 11))


def _scope(path: str, headers: list[tuple[bytes, bytes]]) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), *headers],
        "client": ("testclient", 1),
        "server": ("testserver", 80),
        "state": {},
    }


def _call_without_reading(scope: dict) -> tuple[int, dict, list[int]]:
    """Run the real application; record whether any body was requested."""
    reads: list[int] = []
    sent: list[dict] = []

    async def receive():
        reads.append(1)
        return {"type": "http.request", "body": b"x" * 65536, "more_body": True}

    async def send(message):
        sent.append(message)

    asyncio.run(main_app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    return start["status"], json.loads(body), reads


@pytest.mark.parametrize(
    "path",
    [
        f"{API}/knowledge/upload",
        f"{API}/payments/{uuid.uuid4()}/evidence",
        f"{API}/hotel/catalog/room-types/{uuid.uuid4()}/images",
    ],
)
def test_upload_without_a_token_is_refused_before_any_body_is_read(path):
    status, body, reads = _call_without_reading(
        _scope(path, [(b"content-type", b"multipart/form-data; boundary=b")])
    )
    assert status == 401
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert reads == []


def _expired_token() -> str:
    settings = get_settings()
    past = datetime.now(UTC) - timedelta(minutes=5)
    return jwt.encode(
        {"sub": str(uuid.uuid4()), "iat": past, "exp": past},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer not-a-token",
        "Basic dXNlcjpwYXNz",
        "Bearer",
        f"Bearer {jwt.encode({'sub': 'x', 'exp': 4102444800}, 'w' * 32)}",
        "expired",
        "no-subject",
    ],
)
def test_pre_authorization_gives_the_same_answer_as_get_current_user(
    client, authorization
):
    settings = get_settings()
    if authorization == "expired":
        authorization = f"Bearer {_expired_token()}"
    elif authorization == "no-subject":
        authorization = "Bearer " + jwt.encode(
            {"exp": 4102444800, "sub": ""},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
    status, body, reads = _call_without_reading(
        _scope(
            f"{API}/knowledge/upload",
            [
                (b"authorization", authorization.encode()),
                (b"content-type", b"multipart/form-data; boundary=b"),
            ],
        )
    )
    reference = client.get(f"{API}/auth/me", headers={"Authorization": authorization})
    assert status == reference.status_code == 401
    assert body["error"] == reference.json()["error"]
    assert reads == []


def test_valid_token_is_let_through_to_the_full_dependency_checks(client_db):
    # A correctly signed token for a user that does not exist passes the
    # header check; the dependency's user lookup still refuses it.
    token = create_access_token(
        user_id=uuid.uuid4(), email="ghost@example.com", token_version=0
    )
    response = client_db.post(
        f"{API}/knowledge/upload",
        headers=_bearer(token),
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert response.status_code in {401, 404}
    assert response.json()["error"]["code"] != "REQUEST_BODY_TOO_LARGE"


# -------------------------------------------------------- upload routes


def test_payment_evidence_body_over_the_limit_is_refused(client_db, evidence_storage):
    _, token = register_verify_and_login(client_db, email="evidence-big@example.com")
    settings = get_settings()
    oversized = JPEG + b"0" * (
        settings.PAYMENT_EVIDENCE_MAX_FILE_SIZE_BYTES
        + settings.UPLOAD_REQUEST_OVERHEAD_BYTES
    )
    response = client_db.post(
        f"{API}/payments/{uuid.uuid4()}/evidence",
        headers=_bearer(token),
        files={"file": ("slip.jpg", oversized, "image/jpeg")},
    )
    _assert_too_large(response)
    assert [path for path in evidence_storage.rglob("*") if path.is_file()] == []


def test_payment_evidence_within_the_limit_reaches_the_endpoint(
    client_db, evidence_storage
):
    _, token = register_verify_and_login(client_db, email="evidence-ok@example.com")
    response = client_db.post(
        f"{API}/payments/{uuid.uuid4()}/evidence",
        headers=_bearer(token),
        files={"file": ("slip.jpg", JPEG + b"small", "image/jpeg")},
    )
    # The unknown payment is reported by the service, not by the size limit.
    assert response.status_code == 404
    assert response.json()["error"]["code"] != "REQUEST_BODY_TOO_LARGE"


def test_room_image_body_over_the_limit_is_refused(client_db):
    _, token = register_verify_and_login(client_db, email="image-big@example.com")
    oversized = JPEG + b"0" * (
        ROOM_IMAGE_MAX_BYTES + get_settings().UPLOAD_REQUEST_OVERHEAD_BYTES
    )
    response = client_db.post(
        f"{API}/hotel/catalog/room-types/{uuid.uuid4()}/images",
        headers=_bearer(token),
        data={"alt_text": "room"},
        files={"file": ("room.jpg", oversized, "image/jpeg")},
    )
    _assert_too_large(response)


# ----------------------------------------------------- webhooks, default


def test_channel_webhook_body_over_the_limit_is_refused(client_db):
    limit = get_settings().CHANNEL_WEBHOOK_MAX_BYTES
    for provider in ("line", "facebook"):
        response = client_db.post(
            f"{API}/channels/webhooks/{provider}/{uuid.uuid4()}",
            content=b"{" + b" " * limit + b"}",
            headers={"Content-Type": "application/json"},
        )
        _assert_too_large(response)


def test_channel_webhook_within_the_limit_reaches_the_handler(client_db):
    response = client_db.post(
        f"{API}/channels/webhooks/line/{uuid.uuid4()}",
        content=b"{}",
        headers={"Content-Type": "application/json", "X-Line-Signature": "x"},
    )
    assert response.status_code != 413


def test_default_limit_bounds_unauthenticated_json_routes(client):
    limit = get_settings().REQUEST_BODY_DEFAULT_MAX_BYTES
    padded = json.dumps({"email": "a@example.com", "password": "x" * limit})
    _assert_too_large(client.post(f"{API}/auth/login", content=padded))


def test_default_limit_covers_chunked_bodies_without_a_length():
    reached: list[int] = []
    app = FastAPI()

    @app.post("/json")
    async def echo(request: Request) -> dict:
        reached.append(1)
        return {"size": len(await request.body())}

    app.add_middleware(BodySizeLimitMiddleware, default_max_bytes=4096)
    chunks = [b"x" * 1024] * 64
    sent: list[dict] = []

    async def receive():
        body = chunks.pop(0) if chunks else b""
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message):
        sent.append(message)

    asyncio.run(app(_scope("/json", []), receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 413
    assert chunks, "the rest of the body was never read"
    assert reached == [1]  # the handler started reading, then was cut off
