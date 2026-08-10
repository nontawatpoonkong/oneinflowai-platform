"""Workspace-scoped customer payment persistence."""

from sqlalchemy import select

from app.models.payment import (
    Payment,
    PaymentDestination,
    PaymentEvidence,
    PaymentVerification,
)
from app.repositories.base import BaseRepository


class PaymentDestinationRepository(BaseRepository[PaymentDestination]):
    model = PaymentDestination

    async def get(self, workspace_id, destination_id):
        return await self.session.scalar(
            select(PaymentDestination).where(
                PaymentDestination.workspace_id == workspace_id,
                PaymentDestination.id == destination_id,
            )
        )

    async def list(self, workspace_id):
        result = await self.session.execute(
            select(PaymentDestination)
            .where(PaymentDestination.workspace_id == workspace_id)
            .order_by(
                PaymentDestination.is_default.desc(), PaymentDestination.created_at
            )
        )
        return list(result.scalars())


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    async def get(self, workspace_id, payment_id):
        return await self.session.scalar(
            select(Payment).where(
                Payment.workspace_id == workspace_id, Payment.id == payment_id
            )
        )

    async def get_idempotent(self, workspace_id, key):
        return await self.session.scalar(
            select(Payment).where(
                Payment.workspace_id == workspace_id,
                Payment.idempotency_key == key,
            )
        )

    async def list(self, workspace_id):
        result = await self.session.execute(
            select(Payment)
            .where(Payment.workspace_id == workspace_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars())


class PaymentEvidenceRepository(BaseRepository[PaymentEvidence]):
    model = PaymentEvidence

    async def get(self, workspace_id, evidence_id):
        return await self.session.scalar(
            select(PaymentEvidence).where(
                PaymentEvidence.workspace_id == workspace_id,
                PaymentEvidence.id == evidence_id,
            )
        )

    async def get_for_payment(self, workspace_id, payment_id):
        return await self.session.scalar(
            select(PaymentEvidence)
            .where(
                PaymentEvidence.workspace_id == workspace_id,
                PaymentEvidence.payment_id == payment_id,
            )
            .order_by(PaymentEvidence.created_at.desc())
            .limit(1)
        )

    async def get_by_hash(self, workspace_id, content_hash):
        return await self.session.scalar(
            select(PaymentEvidence).where(
                PaymentEvidence.workspace_id == workspace_id,
                PaymentEvidence.content_hash == content_hash,
            )
        )


class PaymentVerificationRepository(BaseRepository[PaymentVerification]):
    model = PaymentVerification

    async def get_transfer(self, workspace_id, provider, reference):
        return await self.session.scalar(
            select(PaymentVerification).where(
                PaymentVerification.workspace_id == workspace_id,
                PaymentVerification.provider == provider,
                PaymentVerification.transfer_reference == reference,
            )
        )

    async def list(self, workspace_id, payment_id):
        result = await self.session.execute(
            select(PaymentVerification)
            .where(
                PaymentVerification.workspace_id == workspace_id,
                PaymentVerification.payment_id == payment_id,
            )
            .order_by(PaymentVerification.created_at)
        )
        return list(result.scalars())
