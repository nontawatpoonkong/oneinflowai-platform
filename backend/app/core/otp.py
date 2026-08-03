"""Secure one-time-password primitives."""

import hashlib
import hmac
import secrets


def generate_numeric_otp() -> str:
    """Return exactly six cryptographically random numeric digits."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(*, otp: str, secret: str) -> str:
    return hmac.new(secret.encode(), otp.encode(), hashlib.sha256).hexdigest()


def verify_otp(*, otp: str, expected_hash: str, secret: str) -> bool:
    candidate = hash_otp(otp=otp, secret=secret)
    return hmac.compare_digest(candidate, expected_hash)
