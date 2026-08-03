"""Verification challenge repository."""

import uuid
from datetime import datetime

from sqlalchemy import select, update

from app.models.verification_challenge import (
    VerificationChallenge,
    VerificationPurpose,
)
from app.repositories.base import BaseRepository


class VerificationChallengeRepository(BaseRepository[VerificationChallenge]):
    model = VerificationChallenge

    async def get_latest_for_update(
        self, user_id: uuid.UUID, purpose: VerificationPurpose
    ) -> VerificationChallenge | None:
        stmt = (
            select(VerificationChallenge)
            .where(
                VerificationChallenge.user_id == user_id,
                VerificationChallenge.purpose == purpose,
            )
            .order_by(VerificationChallenge.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def invalidate_active(
        self,
        user_id: uuid.UUID,
        purpose: VerificationPurpose,
        used_at: datetime,
    ) -> None:
        await self.session.execute(
            update(VerificationChallenge)
            .where(
                VerificationChallenge.user_id == user_id,
                VerificationChallenge.purpose == purpose,
                VerificationChallenge.used_at.is_(None),
            )
            .values(used_at=used_at)
        )
