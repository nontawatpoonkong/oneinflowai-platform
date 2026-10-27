"""Security primitives: password hashing (bcrypt) and JWT (HS256)."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Every token this server issues carries these claims; a token without them is
# refused instead of being treated as never expiring.
_REQUIRED_CLAIMS = ["exp", "sub"]

# bcrypt operates on at most 72 bytes; longer inputs are truncated to stay
# within that bound consistently for both hashing and verification.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(*, user_id: uuid.UUID | str, email: str) -> str:
    """Create an HS256 access token with `sub`, `email`, `iat`, `exp`."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> dict:
    """Decode/verify a token. Raises `jwt.PyJWTError` on failure."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": _REQUIRED_CLAIMS},
        )
    except RecursionError as exc:
        # Deeply nested JSON in an attacker-supplied header or payload
        # exhausts the JSON parser before the signature is checked. That is a
        # malformed token, not a server failure. The token is never logged.
        logger.warning("auth.token.malformed", extra={"reason": "nesting"})
        raise jwt.DecodeError("Malformed token") from exc
