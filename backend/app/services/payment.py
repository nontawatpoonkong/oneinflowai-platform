"""Customer payment creation, hardened evidence storage, and verification."""

import hashlib
import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    PaymentDuplicateError,
    PaymentEvidenceError,
    PaymentEvidenceTooLargeError,
    PaymentNotFoundError,
    PaymentValidationError,
    PaymentVerificationInProgressError,
    PaymentVerificationProviderError,
)
from app.integrations.slip_verification import (
    SlipVerificationProvider,
    SlipVerificationProviderError,
    SlipVerificationRequest,
)
from app.models.action import ActionRequest
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.notification import NotificationEntityType, NotificationType
from app.models.payment import (
    Payment,
    PaymentDestination,
    PaymentEvidence,
    PaymentStatus,
    PaymentVerification,
    VerificationStatus,
)
from app.repositories.payment import (
    PaymentDestinationRepository,
    PaymentEvidenceRepository,
    PaymentRepository,
    PaymentVerificationRepository,
)
from app.schemas.payment import (
    PaymentCreate,
    PaymentDestinationCreate,
    PaymentDestinationUpdate,
)
from app.services.entitlement import SLIP_VERIFICATIONS, EntitlementService
from app.services.notification import NotificationService
from app.storage import StorageProvider, create_storage_provider


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: StorageProvider | None = None,
        settings: Settings | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.storage = storage or create_storage_provider(self.settings)
        self.destinations = PaymentDestinationRepository(session)
        self.payments = PaymentRepository(session)
        self.evidence = PaymentEvidenceRepository(session)

    async def create_destination(self, workspace_id, data: PaymentDestinationCreate):
        values = data.model_dump(exclude={"promptpay_identifier"})
        identifier = data.promptpay_identifier
        if data.type.value == "PROMPTPAY" and not identifier:
            raise PaymentValidationError("PromptPay identifier is required")
        if data.is_default:
            await self.session.execute(
                update(PaymentDestination)
                .where(PaymentDestination.workspace_id == workspace_id)
                .values(is_default=False)
            )
        destination = PaymentDestination(
            workspace_id=workspace_id,
            **values,
            promptpay_identifier_protected=hashlib.sha256(
                identifier.encode()
            ).hexdigest()
            if identifier
            else None,
            promptpay_identifier_last4=identifier[-4:] if identifier else None,
        )
        await self.destinations.add(destination)
        await self.session.commit()
        await self.session.refresh(destination)
        return destination

    async def list_destinations(self, workspace_id):
        return await self.destinations.list(workspace_id)

    async def update_destination(
        self, workspace_id, destination_id, data: PaymentDestinationUpdate
    ):
        destination = await self.get_destination(workspace_id, destination_id)
        if data.is_default:
            await self.session.execute(
                update(PaymentDestination)
                .where(PaymentDestination.workspace_id == workspace_id)
                .values(is_default=False)
            )
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(destination, key, value)
        await self.session.commit()
        await self.session.refresh(destination)
        return destination

    async def get_destination(self, workspace_id, destination_id):
        value = await self.destinations.get(workspace_id, destination_id)
        if not value:
            raise PaymentNotFoundError("Payment destination not found")
        return value

    async def create(self, workspace_id, data: PaymentCreate):
        if data.idempotency_key and (
            existing := await self.payments.get_idempotent(
                workspace_id, data.idempotency_key
            )
        ):
            return existing
        destination = await self.get_destination(
            workspace_id, data.payment_destination_id
        )
        if not destination.is_active:
            raise PaymentValidationError("Payment destination is inactive")
        await self._validate_links(workspace_id, data)
        payment = Payment(workspace_id=workspace_id, **data.model_dump())
        await self.payments.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def get(self, workspace_id, payment_id):
        payment = await self.payments.get(workspace_id, payment_id)
        if not payment:
            raise PaymentNotFoundError()
        return payment

    async def list(self, workspace_id, *, page=1, page_size=50):
        return await self.payments.list(
            workspace_id, limit=page_size, offset=(page - 1) * page_size
        )

    async def submit_evidence(self, workspace_id, payment_id, file: UploadFile):
        payment = await self.get(workspace_id, payment_id)
        mime = (file.content_type or "").lower()
        data = await self._read_limited(file)
        if mime == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
            raise PaymentEvidenceError()
        if mime == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise PaymentEvidenceError()
        if mime not in {"image/jpeg", "image/png"}:
            raise PaymentEvidenceError()
        content_hash = hashlib.sha256(data).hexdigest()
        if await self.evidence.get_by_hash(workspace_id, content_hash):
            raise PaymentDuplicateError()
        evidence_id = uuid.uuid4()
        extension = ".jpg" if mime == "image/jpeg" else ".png"
        key = f"payment-evidence/{workspace_id}/{payment.id}/{evidence_id}{extension}"
        evidence = PaymentEvidence(
            id=evidence_id,
            workspace_id=workspace_id,
            payment_id=payment.id,
            storage_key=key,
            mime_type=mime,
            file_size=len(data),
            content_hash=content_hash,
        )
        await self.evidence.add(evidence)
        try:
            await self.storage.save(key=key, data=data)
            await self.session.commit()
            await self.session.refresh(evidence)
        except Exception:
            await self.session.rollback()
            with suppress(Exception):
                await self.storage.delete(key=key)
            raise
        return evidence

    async def get_evidence(self, workspace_id, payment_id):
        await self.get(workspace_id, payment_id)
        evidence = await self.evidence.get_for_payment(workspace_id, payment_id)
        if not evidence:
            raise PaymentEvidenceError("Payment evidence not found")
        return evidence

    async def _read_limited(self, file):
        maximum = self.settings.PAYMENT_EVIDENCE_MAX_FILE_SIZE_BYTES
        data = bytearray()
        while chunk := await file.read(min(65536, maximum + 1 - len(data))):
            data.extend(chunk)
            if len(data) > maximum:
                raise PaymentEvidenceTooLargeError()
        if not data:
            raise PaymentEvidenceError()
        return bytes(data)

    async def _validate_links(self, workspace_id, data):
        for model, identifier, label in (
            (ActionRequest, data.action_request_id, "Action"),
            (Conversation, data.conversation_id, "Conversation"),
            (Customer, data.customer_id, "Customer"),
        ):
            if identifier and not await self.session.scalar(
                select(model.id).where(
                    model.id == identifier, model.workspace_id == workspace_id
                )
            ):
                raise PaymentNotFoundError(f"{label} not found")


class PaymentVerificationService:
    def __init__(
        self,
        session: AsyncSession,
        provider: SlipVerificationProvider,
        *,
        settings: Settings | None = None,
        storage: StorageProvider | None = None,
    ):
        self.session = session
        self.provider = provider
        self.settings = settings or get_settings()
        self.storage = storage or create_storage_provider(self.settings)
        self.payments = PaymentRepository(session)
        self.destinations = PaymentDestinationRepository(session)
        self.evidence = PaymentEvidenceRepository(session)
        self.verifications = PaymentVerificationRepository(session)

    async def verify(self, workspace_id, payment_id):
        payment = await self.payments.get_for_update(workspace_id, payment_id)
        if not payment:
            raise PaymentNotFoundError()
        if payment.status == PaymentStatus.VERIFIED:
            # Reconciliation locks the booking before the payment. Release this
            # payment lock first to preserve that order on repeated requests.
            await self.session.commit()
            await self._reconcile_booking_payment(workspace_id, payment)
            return payment, await self.verifications.latest(workspace_id, payment.id)
        if payment.status == PaymentStatus.VERIFYING:
            raise PaymentVerificationInProgressError()
        if payment.expires_at and payment.expires_at <= datetime.now(UTC):
            payment.status = PaymentStatus.EXPIRED
            await self.session.commit()
            await self.session.refresh(payment)
            return payment, None
        evidence = await self.evidence.get_for_payment(workspace_id, payment.id)
        if not evidence:
            raise PaymentEvidenceError("Payment evidence not found")
        destination = await self.destinations.get(
            workspace_id, payment.payment_destination_id
        )
        content = await self.storage.read(key=evidence.storage_key)
        if (
            len(content) != evidence.file_size
            or hashlib.sha256(content).hexdigest() != evidence.content_hash
        ):
            raise PaymentEvidenceError()
        if self.provider.name == "easyslip_v2" and len(content) > 4 * 1024 * 1024:
            raise PaymentEvidenceTooLargeError()
        if self.provider.name != "development":
            entitlements = EntitlementService(self.session)
            await entitlements.require_capacity(workspace_id, SLIP_VERIFICATIONS)
            await entitlements.record(
                workspace_id, SLIP_VERIFICATIONS, 1, provider=self.provider.name
            )
            # Reserve quota and claim this payment in the same transaction.
            # Release the row/advisory locks before the bounded external call.
        payment.status = PaymentStatus.VERIFYING
        await self.session.commit()
        try:
            result = await self.provider.verify(
                SlipVerificationRequest(
                    content_hash=evidence.content_hash,
                    content=content,
                    mime_type=evidence.mime_type,
                    expected_amount=payment.expected_amount,
                    currency=payment.currency,
                    destination_bank_code=destination.bank_code,
                    destination_bank_name=destination.bank_name,
                    destination_account_name=destination.account_name,
                    destination_account_masked=destination.account_number_masked,
                    destination_promptpay_last4=destination.promptpay_identifier_last4,
                )
            )
        except SlipVerificationProviderError as exc:
            await self._record_provider_error(workspace_id, payment, evidence, exc.code)
            raise PaymentVerificationProviderError() from exc
        except Exception as exc:
            await self._record_provider_error(
                workspace_id,
                payment,
                evidence,
                "PROVIDER_ERROR",
            )
            raise PaymentVerificationProviderError() from exc
        duplicate = result.transfer_reference and await self.verifications.get_transfer(
            workspace_id, result.provider, result.transfer_reference
        )
        amount_match = (
            result.amount == payment.expected_amount
            and result.currency == payment.currency
        )
        receiver_match = self._receiver_matches(destination, result)
        provider_duplicate = result.duplicate_reference_signal is True
        valid = (
            result.is_valid
            and amount_match
            and receiver_match
            and not duplicate
            and not provider_duplicate
        )
        status = VerificationStatus.VALID if valid else VerificationStatus.INVALID
        verification = PaymentVerification(
            workspace_id=workspace_id,
            payment_id=payment.id,
            evidence_id=evidence.id,
            provider=result.provider,
            provider_reference=result.provider_reference,
            status=status,
            reported_amount=result.amount,
            currency=result.currency,
            transfer_reference=None if duplicate else result.transfer_reference,
            transferred_at=result.transferred_at,
            receiver_match=receiver_match,
            amount_match=amount_match,
            error_code="DUPLICATE" if duplicate or provider_duplicate else None,
            verified_at=datetime.now(UTC) if valid else None,
        )
        await self.verifications.add(verification)
        if duplicate or provider_duplicate:
            payment.status = PaymentStatus.DUPLICATE
        elif valid:
            payment.status = PaymentStatus.VERIFIED
            payment.verified_amount = result.amount
            payment.verified_at = verification.verified_at
            payment.paid_at = result.transferred_at
            notifications = NotificationService(self.session)
            recipients = []
            if payment.action_request_id:
                linked_action = await self.session.get(
                    ActionRequest, payment.action_request_id
                )
                if linked_action and linked_action.assigned_to_user_id:
                    recipients = [linked_action.assigned_to_user_id]
            if not recipients:
                recipients = await notifications.administrative_recipients(workspace_id)
            await notifications.create_for_recipients(
                workspace_id,
                recipients,
                type=NotificationType.PAYMENT_VERIFIED,
                title="Customer payment verified",
                body="A customer payment was verified and is ready for review.",
                entity_type=NotificationEntityType.PAYMENT,
                entity_id=payment.id,
                deduplication_key=f"payment-verified:{payment.id}",
            )
        else:
            payment.status = PaymentStatus.REJECTED
        await self.session.commit()
        await self.session.refresh(payment)
        await self.session.refresh(verification)
        if payment.status == PaymentStatus.VERIFIED:
            await self._reconcile_booking_payment(workspace_id, payment)
        return payment, verification

    async def _reconcile_booking_payment(self, workspace_id, payment):
        if payment.booking_id is None:
            return
        # Financial verification is committed first. Booking application is a
        # separate, idempotent transaction owned by the Hotel service boundary.
        from app.services.booking_payment_reconciliation import (
            BookingPaymentReconciliationService,
        )

        await BookingPaymentReconciliationService(self.session).reconcile_payment(
            workspace_id, payment.id
        )
        await self.session.refresh(payment)

    async def _record_provider_error(self, workspace_id, payment, evidence, code):
        payment.status = PaymentStatus.PENDING
        verification = PaymentVerification(
            workspace_id=workspace_id,
            payment_id=payment.id,
            evidence_id=evidence.id,
            provider=self.provider.name,
            status=VerificationStatus.ERROR,
            error_code=code,
        )
        await self.verifications.add(verification)
        await self.session.commit()

    @staticmethod
    def _receiver_matches(destination, result) -> bool:
        def normalized(value):
            return re.sub(r"[^0-9a-zก-๙]", "", (value or "").casefold())

        expected_bank = normalized(destination.bank_code or destination.bank_name)
        actual_bank = normalized(result.receiver_bank)
        if expected_bank and actual_bank and expected_bank != actual_bank:
            return False
        expected_account = normalized(
            destination.account_number_masked or destination.promptpay_identifier_last4
        )
        actual_account = normalized(result.receiver_account_masked)
        visible_expected = expected_account.replace("x", "")
        visible_actual = actual_account.replace("x", "")
        account_match = bool(
            visible_expected
            and visible_actual
            and (
                visible_expected.endswith(visible_actual)
                or visible_actual.endswith(visible_expected)
            )
        )
        name_match = bool(
            normalized(destination.account_name)
            and normalized(destination.account_name) == normalized(result.receiver_name)
        )
        return account_match or name_match

    async def list(self, workspace_id, payment_id, *, page=1, page_size=50):
        if not await self.payments.get(workspace_id, payment_id):
            raise PaymentNotFoundError()
        return await self.verifications.list(
            workspace_id,
            payment_id,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
