"""Authentication service.

Owns registration (User + Workspace + owner WorkspaceMember in one
transaction), login, token issuance, and user lookup.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    InactiveUserError,
    InvalidCredentialsError,
)
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse
from app.services.workspace import WorkspaceService
from app.services.workspace_naming import derive_workspace_naming

settings = get_settings()


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.workspaces = WorkspaceService(session)

    def issue_token(self, user: User) -> TokenResponse:
        token = create_access_token(user_id=user.id, email=user.email)
        return TokenResponse(
            access_token=token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def register(
        self, *, email: str, password: str, full_name: str | None
    ) -> tuple[User, Workspace, TokenResponse]:
        email = email.lower()
        if await self.users.email_exists(email):
            raise EmailAlreadyExistsError()

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
        )
        await self.users.add(user)

        naming = derive_workspace_naming(email=email, full_name=full_name)
        workspace = await self.workspaces.build_with_owner(
            owner_id=user.id,
            name=naming.display_name,
            slug_source=naming.slug_base,
        )

        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(workspace)

        return user, workspace, self.issue_token(user)

    async def login(self, *, email: str, password: str) -> tuple[User, TokenResponse]:
        user = await self.users.get_by_email(email.lower())
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveUserError()
        return user, self.issue_token(user)

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("User no longer exists")
        return user
