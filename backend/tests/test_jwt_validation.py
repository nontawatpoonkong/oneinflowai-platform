"""Access-token validation contract for GET /api/v1/auth/me.

Valid, unexpired HS256 tokens for an active user are accepted. Every other
token is refused with 401 UNAUTHENTICATED (inactive users get 403
INACTIVE_USER), including tokens that are malformed in ways an attacker can
send without credentials: those must never surface as HTTP 500. Tokens are
signed with the test Settings' key; the key itself is never printed.
"""

import asyncio
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.models.user import User
from tests.conftest import TestSessionLocal, register_verify_and_login

ME_URL = "/api/v1/auth/me"
EMAIL = "jwt-user@example.com"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _claims(user_id: str, **overrides):
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "email": EMAIL,
        "ver": 0,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def _sign(claims, *, key=None, algorithm="HS256"):
    settings = get_settings()
    return jwt.encode(claims, key or settings.JWT_SECRET_KEY, algorithm=algorithm)


def _me(client, token):
    return client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})


def _assert_unauthenticated(response, message=None):
    assert response.status_code == 401, response.text
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "UNAUTHENTICATED"
    if message:
        assert body["message"] == message


@pytest.fixture
def user_id(client_db):
    user, _ = register_verify_and_login(client_db, email=EMAIL)
    return user["user"]["id"]


def test_valid_unexpired_token_is_accepted(client_db, user_id):
    response = _me(client_db, _sign(_claims(user_id)))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["id"] == user_id
    assert response.json()["data"]["email"] == EMAIL


def test_expired_token_is_refused(client_db, user_id):
    past = datetime.now(UTC) - timedelta(minutes=10)
    token = _sign(_claims(user_id, iat=past, exp=past + timedelta(minutes=1)))
    _assert_unauthenticated(_me(client_db, token), "Token has expired")


def test_wrong_signature_is_refused(client_db, user_id):
    token = _sign(_claims(user_id), key="another-key-of-at-least-32-bytes-long!!")
    _assert_unauthenticated(_me(client_db, token), "Invalid token")
    header, payload, _ = _sign(_claims(user_id)).split(".")
    _assert_unauthenticated(_me(client_db, f"{header}.{payload}.AAAA"), "Invalid token")


@pytest.mark.parametrize("algorithm", ["HS512", "HS384"])
def test_algorithms_other_than_the_configured_one_are_refused(
    client_db, user_id, algorithm
):
    token = _sign(_claims(user_id), algorithm=algorithm)
    _assert_unauthenticated(_me(client_db, token), "Invalid token")


def test_unsigned_none_algorithm_token_is_refused(client_db, user_id):
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(
        json.dumps(
            {"sub": user_id, "exp": int(datetime.now(UTC).timestamp()) + 300}
        ).encode()
    )
    _assert_unauthenticated(_me(client_db, f"{header}.{payload}."), "Invalid token")


@pytest.mark.parametrize("missing", ["exp", "sub", "ver"])
def test_token_without_required_claims_is_refused(client_db, user_id, missing):
    # The server always issues exp, sub and ver; a signed token without them
    # is not one of ours. Without ver it could never be revoked, so tokens
    # issued before token versions existed are refused, not grandfathered.
    token = _sign(_claims(user_id, **{missing: None}))
    _assert_unauthenticated(_me(client_db, token))


def test_inactive_user_is_refused_even_with_a_valid_token(client_db, user_id):
    token = _sign(_claims(user_id))

    async def deactivate():
        async with TestSessionLocal() as session:
            await session.execute(
                update(User)
                .where(User.id == uuid.UUID(user_id))
                .values(is_active=False)
            )
            await session.commit()

    asyncio.run(deactivate())
    response = _me(client_db, token)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "INACTIVE_USER"
    assert EMAIL not in response.text


def test_deeply_nested_header_is_refused_without_server_error(client_db, user_id):
    depth = 3000
    header = b'{"alg":"HS256","x":' + b"[" * depth + b"]" * depth + b"}"
    token = f"{_b64(header)}.{_b64(b'{}')}.AAAA"
    _assert_unauthenticated(_me(client_db, token), "Invalid token")
    nested_payload = b'{"sub":' + b"[" * depth + b"]" * depth + b"}"
    header_ok = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    _assert_unauthenticated(
        _me(client_db, f"{header_ok}.{_b64(nested_payload)}.AAAA"), "Invalid token"
    )


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        "a.b",
        "a.b.c.d",
        "%%%.%%%.%%%",
        _b64(b"[]") + "." + _b64(b"{}") + ".AAAA",
        _b64(b'{"alg":"HS256"}') + "." + _b64(b"not json") + ".AAAA",
    ],
    ids=[
        "no-dots",
        "two-parts",
        "four-parts",
        "bad-base64",
        "array-header",
        "bad-json",
    ],
)
def test_generally_malformed_tokens_are_refused(client_db, user_id, token):
    _assert_unauthenticated(_me(client_db, token), "Invalid token")


async def _set_token_version(user_id: str, version: int) -> None:
    async with TestSessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.id == uuid.UUID(user_id))
            .values(token_version=version)
        )
        await session.commit()


@pytest.mark.parametrize("version", ["0", 0.0, True, False, -1, None, [0]])
def test_token_version_must_be_a_non_negative_integer(client_db, user_id, version):
    claims = _claims(user_id)
    claims["ver"] = version
    # A null ver is a missing required claim to PyJWT; the rest fail our check.
    message = "Invalid token" if version is None else "Invalid token payload"
    _assert_unauthenticated(_me(client_db, _sign(claims)), message)


def test_token_from_an_older_version_is_revoked(client_db, user_id):
    old_token = _sign(_claims(user_id, ver=0))
    asyncio.run(_set_token_version(user_id, 1))
    _assert_unauthenticated(_me(client_db, old_token), "Token has been revoked")
    assert _me(client_db, _sign(_claims(user_id, ver=1))).status_code == 200


def test_a_version_ahead_of_the_user_is_refused(client_db, user_id):
    # Only the server can mint versions; one the user has not reached is not
    # a token this server issued for the current state.
    _assert_unauthenticated(
        _me(client_db, _sign(_claims(user_id, ver=5))), "Token has been revoked"
    )


def test_editing_ver_without_the_key_breaks_the_signature(client_db, user_id):
    asyncio.run(_set_token_version(user_id, 3))
    header, _, signature = _sign(_claims(user_id, ver=0)).split(".")
    forged = _b64(
        json.dumps(
            {
                "sub": user_id,
                "ver": 3,
                "exp": int(datetime.now(UTC).timestamp()) + 300,
            }
        ).encode()
    )
    forged_token = f"{header}.{forged}.{signature}"
    _assert_unauthenticated(_me(client_db, forged_token), "Invalid token")


def test_login_issues_a_token_for_the_current_version(client_db):
    user, token = register_verify_and_login(client_db, email="versioned@example.com")
    asyncio.run(_set_token_version(user["user"]["id"], 4))
    _assert_unauthenticated(_me(client_db, token), "Token has been revoked")
    login = client_db.post(
        "/api/v1/auth/login",
        json={"email": "versioned@example.com", "password": "supersecret123"},
    )
    fresh = login.json()["data"]["access_token"]
    assert jwt.decode(fresh, options={"verify_signature": False})["ver"] == 4
    assert _me(client_db, fresh).status_code == 200
