"""Authentication dependencies."""

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.types import Scope

from app.core import context
from app.core.exceptions import AuthenticationError, InactiveUserError
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.user import User
from app.services.auth import AuthService

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    token_version: int


def claims_from_access_token(token: str) -> AccessTokenClaims:
    """Verify an access token and return its subject and version; no database."""
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token") from exc

    subject = payload.get("sub")
    if not subject:
        raise AuthenticationError("Invalid token payload")
    version = payload.get("ver")
    # bool is an int subclass; only a plain non-negative integer is ours.
    if type(version) is not int or version < 0:
        raise AuthenticationError("Invalid token payload")

    try:
        return AccessTokenClaims(uuid.UUID(subject), version)
    except ValueError as exc:
        raise AuthenticationError("Invalid token subject") from exc


def preauthorize_bearer(scope: Scope) -> AuthenticationError | None:
    """Refuse, from the headers alone, a request `get_current_user` would refuse.

    Used before an upload body is read. It parses the header as `HTTPBearer`
    does and applies the same token checks; the user lookup and every
    Workspace authorization check still run in the dependencies afterwards.
    """
    authorization = Headers(scope=scope).get("authorization")
    scheme, token = get_authorization_scheme_param(authorization)
    if not (authorization and scheme and token) or scheme.lower() != "bearer":
        return AuthenticationError("Missing bearer token")
    try:
        claims_from_access_token(token)
    except AuthenticationError as exc:
        return exc
    return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthenticationError("Missing bearer token")

    claims = claims_from_access_token(credentials.credentials)

    user = await AuthService(session).get_user_by_id(claims.user_id)
    if not user.is_active:
        raise InactiveUserError()
    # Read on every request, so a revocation committed by any instance holds
    # for the next request everywhere.
    if claims.token_version != user.token_version:
        raise AuthenticationError("Token has been revoked")

    # Populate logging context for the remainder of the request.
    context.set_user_id(str(user.id))
    return user
