"""Secure password-reset challenge and one-time authorization lifecycle."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    InvalidPasswordResetCodeError,
    InvalidPasswordResetTokenError,
    VerificationConfigurationError,
)
from app.core.otp import generate_numeric_otp, hash_otp, verify_otp
from app.core.security import hash_password
from app.integrations.email.base import EmailProvider
from app.models.password_reset_session import PasswordResetSession
from app.models.user import User
from app.models.verification_challenge import (
    VerificationChallenge,
    VerificationPurpose,
)
from app.repositories.password_reset_session import PasswordResetSessionRepository
from app.repositories.user import UserRepository
from app.repositories.verification_challenge import VerificationChallengeRepository


@dataclass(frozen=True, slots=True)
class PendingPasswordResetEmail:
    recipient: str
    otp: str
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class ResetAuthorization:
    token: str
    expires_in_seconds: int


class PasswordResetService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.users = UserRepository(session)
        self.challenges = VerificationChallengeRepository(session)
        self.reset_sessions = PasswordResetSessionRepository(session)

    def _secret(self) -> str:
        secret = (self.settings.OTP_HASH_SECRET or "").strip()
        if not secret:
            raise VerificationConfigurationError()
        return secret

    def _token_hash(self, token: str) -> str:
        return hash_otp(otp=f"password-reset-token:{token}", secret=self._secret())

    async def request(self, email: str) -> PendingPasswordResetEmail | None:
        user = await self.users.get_by_email(email.lower())
        if (
            user is None
            or not user.is_active
            or not user.email_verified
        ):
            await self.session.rollback()
            return None

        now = datetime.now(UTC)
        latest = await self.challenges.get_latest_for_update(
            user.id, VerificationPurpose.PASSWORD_RESET
        )
        if latest is not None and latest.resend_available_at > now:
            await self.session.rollback()
            return None

        await self.challenges.invalidate_active(
            user.id, VerificationPurpose.PASSWORD_RESET, now
        )
        await self.reset_sessions.invalidate_active(user.id, now)
        otp = generate_numeric_otp()
        self.session.add(
            VerificationChallenge(
                user_id=user.id,
                purpose=VerificationPurpose.PASSWORD_RESET,
                code_hash=hash_otp(otp=otp, secret=self._secret()),
                expires_at=now
                + timedelta(
                    seconds=self.settings.EMAIL_VERIFICATION_OTP_TTL_SECONDS
                ),
                failed_attempts=0,
                max_attempts=self.settings.EMAIL_VERIFICATION_MAX_ATTEMPTS,
                resend_available_at=now
                + timedelta(
                    seconds=(
                        self.settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
                    )
                ),
            )
        )
        await self.session.commit()
        return PendingPasswordResetEmail(
            recipient=user.email,
            otp=otp,
            expires_in_seconds=self.settings.EMAIL_VERIFICATION_OTP_TTL_SECONDS,
        )

    async def deliver(
        self,
        provider: EmailProvider,
        pending: PendingPasswordResetEmail | None,
    ) -> None:
        if pending is None:
            return
        await provider.send_password_reset_otp(
            recipient=pending.recipient,
            otp=pending.otp,
            expires_in_seconds=pending.expires_in_seconds,
        )

    async def verify(self, *, email: str, otp: str) -> ResetAuthorization:
        user = await self.users.get_by_email(email.lower())
        if user is None or not user.is_active or not user.email_verified:
            await self.session.rollback()
            raise InvalidPasswordResetCodeError()

        challenge = await self.challenges.get_latest_for_update(
            user.id, VerificationPurpose.PASSWORD_RESET
        )
        now = datetime.now(UTC)
        if (
            challenge is None
            or challenge.used_at is not None
            or challenge.expires_at <= now
            or challenge.failed_attempts >= challenge.max_attempts
        ):
            await self.session.rollback()
            raise InvalidPasswordResetCodeError()

        if not verify_otp(
            otp=otp,
            expected_hash=challenge.code_hash,
            secret=self._secret(),
        ):
            challenge.failed_attempts += 1
            await self.session.commit()
            raise InvalidPasswordResetCodeError()

        challenge.used_at = now
        await self.challenges.invalidate_active(
            user.id, VerificationPurpose.PASSWORD_RESET, now
        )
        await self.reset_sessions.invalidate_active(user.id, now)
        token = secrets.token_urlsafe(32)
        self.session.add(
            PasswordResetSession(
                user_id=user.id,
                challenge_id=challenge.id,
                token_hash=self._token_hash(token),
                expires_at=now
                + timedelta(seconds=self.settings.PASSWORD_RESET_TOKEN_TTL_SECONDS),
            )
        )
        await self.session.commit()
        return ResetAuthorization(
            token=token,
            expires_in_seconds=self.settings.PASSWORD_RESET_TOKEN_TTL_SECONDS,
        )

    async def reset(self, *, reset_token: str, new_password: str) -> None:
        reset_session = await self.reset_sessions.get_by_hash_for_update(
            self._token_hash(reset_token)
        )
        now = datetime.now(UTC)
        if (
            reset_session is None
            or reset_session.used_at is not None
            or reset_session.expires_at <= now
        ):
            await self.session.rollback()
            raise InvalidPasswordResetTokenError()

        user = await self.session.get(
            User, reset_session.user_id, with_for_update=True
        )
        if user is None or not user.is_active:
            await self.session.rollback()
            raise InvalidPasswordResetTokenError()

        user.hashed_password = hash_password(new_password)
        user.token_version += 1
        reset_session.used_at = now
        await self.reset_sessions.invalidate_active(user.id, now)
        await self.challenges.invalidate_active(
            user.id, VerificationPurpose.PASSWORD_RESET, now
        )
        await self.session.commit()
