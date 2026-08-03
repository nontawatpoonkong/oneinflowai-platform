"""Email verification challenge lifecycle."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    InvalidVerificationCodeError,
    VerificationConfigurationError,
)
from app.core.otp import generate_numeric_otp, hash_otp, verify_otp
from app.integrations.email.base import EmailProvider
from app.models.user import User
from app.models.verification_challenge import (
    VerificationChallenge,
    VerificationPurpose,
)
from app.repositories.user import UserRepository
from app.repositories.verification_challenge import (
    VerificationChallengeRepository,
)


@dataclass(frozen=True, slots=True)
class PendingVerificationEmail:
    recipient: str
    otp: str
    expires_in_seconds: int


class EmailVerificationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.users = UserRepository(session)
        self.challenges = VerificationChallengeRepository(session)

    def _secret(self) -> str:
        secret = (self.settings.OTP_HASH_SECRET or "").strip()
        if not secret:
            raise VerificationConfigurationError()
        return secret

    async def create_challenge(self, user: User) -> PendingVerificationEmail:
        now = datetime.now(UTC)
        otp = generate_numeric_otp()
        challenge = VerificationChallenge(
            user_id=user.id,
            purpose=VerificationPurpose.EMAIL_VERIFICATION,
            code_hash=hash_otp(otp=otp, secret=self._secret()),
            expires_at=now
            + timedelta(seconds=self.settings.EMAIL_VERIFICATION_OTP_TTL_SECONDS),
            failed_attempts=0,
            max_attempts=self.settings.EMAIL_VERIFICATION_MAX_ATTEMPTS,
            resend_available_at=now
            + timedelta(
                seconds=self.settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
            ),
        )
        await self.challenges.add(challenge)
        return PendingVerificationEmail(
            recipient=user.email,
            otp=otp,
            expires_in_seconds=self.settings.EMAIL_VERIFICATION_OTP_TTL_SECONDS,
        )

    async def resend(self, email: str) -> PendingVerificationEmail | None:
        user = await self.users.get_by_email(email.lower())
        if user is None or user.email_verified:
            await self.session.rollback()
            return None

        now = datetime.now(UTC)
        latest = await self.challenges.get_latest_for_update(
            user.id, VerificationPurpose.EMAIL_VERIFICATION
        )
        if latest is not None and latest.resend_available_at > now:
            await self.session.rollback()
            return None

        await self.challenges.invalidate_active(
            user.id, VerificationPurpose.EMAIL_VERIFICATION, now
        )
        pending = await self.create_challenge(user)
        await self.session.commit()
        return pending

    async def verify(self, *, email: str, otp: str) -> User:
        user = await self.users.get_by_email(email.lower())
        if user is None or user.email_verified:
            await self.session.rollback()
            raise InvalidVerificationCodeError()

        challenge = await self.challenges.get_latest_for_update(
            user.id, VerificationPurpose.EMAIL_VERIFICATION
        )
        now = datetime.now(UTC)
        if (
            challenge is None
            or challenge.used_at is not None
            or challenge.expires_at <= now
            or challenge.failed_attempts >= challenge.max_attempts
        ):
            await self.session.rollback()
            raise InvalidVerificationCodeError()

        if not verify_otp(
            otp=otp,
            expected_hash=challenge.code_hash,
            secret=self._secret(),
        ):
            challenge.failed_attempts += 1
            await self.session.commit()
            raise InvalidVerificationCodeError()

        challenge.used_at = now
        user.email_verified = True
        user.email_verified_at = now
        await self.challenges.invalidate_active(
            user.id, VerificationPurpose.EMAIL_VERIFICATION, now
        )
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def deliver(
        self,
        provider: EmailProvider,
        pending: PendingVerificationEmail | None,
    ) -> None:
        if pending is None:
            return
        await provider.send_verification_otp(
            recipient=pending.recipient,
            otp=pending.otp,
            expires_in_seconds=pending.expires_in_seconds,
        )
