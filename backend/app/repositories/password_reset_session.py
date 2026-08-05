"""Password-reset session persistence."""

import uuid
from datetime import datetime

from sqlalchemy import select, update

from app.models.password_reset_session import PasswordResetSession
from app.repositories.base import BaseRepository


class PasswordResetSessionRepository(BaseRepository[PasswordResetSession]):
    model = PasswordResetSession

    async def get_by_hash_for_update(
        self, token_hash: str
    ) -> PasswordResetSession | None:
        result = await self.session.execute(
            select(PasswordResetSession)
            .where(PasswordResetSession.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def invalidate_active(self, user_id: uuid.UUID, used_at: datetime) -> None:
        await self.session.execute(
            update(PasswordResetSession)
            .where(
                PasswordResetSession.user_id == user_id,
                PasswordResetSession.used_at.is_(None),
            )
            .values(used_at=used_at)
        )
