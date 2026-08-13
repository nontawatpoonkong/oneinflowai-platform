"""Authentication service.

Owns account registration, login, token issuance, and user lookup.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    EmailNotVerifiedError,
    InactiveUserError,
    InvalidCredentialsError,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.integrations.email import (
    EmailDeliveryError,
    EmailProvider,
    create_email_provider,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse
from app.services.email_verification import EmailVerificationService

settings = get_settings()
logger = get_logger(__name__)


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        email_provider: EmailProvider | None = None,
    ) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.email_provider = email_provider or create_email_provider()
        self.verification = EmailVerificationService(session)

    def issue_token(self, user: User) -> TokenResponse:
        token = create_access_token(user_id=user.id, email=user.email)
        return TokenResponse(
            access_token=token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def register(
        self, *, email: str, password: str, full_name: str | None
    ) -> User:
        email = email.lower()
        if await self.users.email_exists(email):
            raise EmailAlreadyExistsError()

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
        )
        await self.users.add(user)

        pending_email = await self.verification.create_challenge(user)

        await self.session.commit()
        await self.session.refresh(user)

        try:
            await self.verification.deliver(self.email_provider, pending_email)
        except EmailDeliveryError:
            logger.warning(
                "verification_email_delivery_failed",
                extra={
                    "event": "verification_email_delivery_failed",
                    "user_id": user.id,
                },
            )

        return user

    async def login(self, *, email: str, password: str) -> tuple[User, TokenResponse]:
        user = await self.users.get_by_email(email.lower())
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveUserError()
        if not user.email_verified:
            raise EmailNotVerifiedError()
        return user, self.issue_token(user)

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("User no longer exists")
        return user
