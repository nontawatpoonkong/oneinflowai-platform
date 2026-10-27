"""Authenticated workspace-scoped customer payment routes."""

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.action.router import require_link_access
from app.auth.dependencies import get_current_user
from app.core.exceptions import WorkspaceAccessDeniedError
from app.database.session import get_db
from app.integrations.slip_verification import create_slip_verification_provider
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.payment import (
    PaymentCreate,
    PaymentDestinationCreate,
    PaymentDestinationResponse,
    PaymentDestinationUpdate,
    PaymentEvidenceResponse,
    PaymentResponse,
    PaymentVerificationResponse,
)
from app.schemas.response import success_response
from app.services.payment import PaymentService, PaymentVerificationService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import require_workspace_capability

router = APIRouter()

_payment_read = require_workspace_capability(WorkspaceCapability.PAYMENT_READ)
_payment_review = require_workspace_capability(WorkspaceCapability.PAYMENT_REVIEW)


async def _payment_reviewer(
    workspace: Workspace = Depends(_payment_review),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Workspace:
    """Payment changes need payment.review and payment.read.

    Every change returns the destination or payment it touched, so reviewers
    must also be allowed to read payments.
    """

    await WorkspaceCapabilityService(session).require(
        workspace.id, user.id, WorkspaceCapability.PAYMENT_READ
    )
    return workspace


def _destination(value):
    return PaymentDestinationResponse.model_validate(value).model_dump(mode="json")


def _payment(value):
    return PaymentResponse.model_validate(value).model_dump(mode="json")


@router.post("/destinations", status_code=status.HTTP_201_CREATED)
async def create_destination(
    payload: PaymentDestinationCreate,
    workspace: Workspace = Depends(_payment_reviewer),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _destination(
            await PaymentService(session).create_destination(workspace.id, payload)
        ),
        "Payment destination created",
    )


@router.get("/destinations")
async def list_destinations(
    workspace: Workspace = Depends(_payment_read),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        [
            _destination(item)
            for item in await PaymentService(session).list_destinations(workspace.id)
        ]
    )


@router.patch("/destinations/{destination_id}")
async def update_destination(
    destination_id: uuid.UUID,
    payload: PaymentDestinationUpdate,
    workspace: Workspace = Depends(_payment_reviewer),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _destination(
            await PaymentService(session).update_destination(
                workspace.id, destination_id, payload
            )
        )
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: PaymentCreate,
    workspace: Workspace = Depends(_payment_reviewer),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    # Linking a guest record or an Action needs the right to read it, checked
    # before the id is looked up so existence is not revealed.
    _, capabilities = await WorkspaceCapabilityService(session).effective(
        workspace.id, user.id
    )
    require_link_access(
        capabilities,
        customer_id=payload.customer_id,
        conversation_id=payload.conversation_id,
    )
    if (
        payload.action_request_id is not None
        and WorkspaceCapability.ACTION_READ not in capabilities
    ):
        raise WorkspaceAccessDeniedError(
            f"Workspace capability required: {WorkspaceCapability.ACTION_READ.value}"
        )
    return success_response(
        _payment(await PaymentService(session).create(workspace.id, payload)),
        "Payment created",
    )


@router.get("")
async def list_payments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    workspace: Workspace = Depends(_payment_read),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        [
            _payment(item)
            for item in await PaymentService(session).list(
                workspace.id, page=page, page_size=page_size
            )
        ]
    )


@router.get("/{payment_id}")
async def get_payment(
    payment_id: uuid.UUID,
    workspace: Workspace = Depends(_payment_read),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _payment(await PaymentService(session).get(workspace.id, payment_id))
    )


@router.post("/{payment_id}/evidence", status_code=status.HTTP_201_CREATED)
async def submit_evidence(
    payment_id: uuid.UUID,
    file: UploadFile = File(...),
    workspace: Workspace = Depends(_payment_reviewer),
    session: AsyncSession = Depends(get_db),
):
    evidence = await PaymentService(session).submit_evidence(
        workspace.id, payment_id, file
    )
    return success_response(
        PaymentEvidenceResponse.model_validate(
            evidence, from_attributes=True
        ).model_dump(mode="json"),
        "Payment evidence submitted",
    )


@router.get("/{payment_id}/evidence")
async def get_evidence(
    payment_id: uuid.UUID,
    workspace: Workspace = Depends(_payment_read),
    session: AsyncSession = Depends(get_db),
):
    evidence = await PaymentService(session).get_evidence(workspace.id, payment_id)
    return success_response(
        PaymentEvidenceResponse.model_validate(
            evidence, from_attributes=True
        ).model_dump(mode="json")
    )


@router.post("/{payment_id}/verify")
async def verify_payment(
    payment_id: uuid.UUID,
    workspace: Workspace = Depends(_payment_reviewer),
    session: AsyncSession = Depends(get_db),
):
    payment, verification = await PaymentVerificationService(
        session, create_slip_verification_provider()
    ).verify(workspace.id, payment_id)
    return success_response(
        {
            "payment": _payment(payment),
            "verification": PaymentVerificationResponse.model_validate(
                verification, from_attributes=True
            ).model_dump(mode="json")
            if verification
            else None,
        }
    )


@router.get("/{payment_id}/verifications")
async def list_verifications(
    payment_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    workspace: Workspace = Depends(_payment_read),
    session: AsyncSession = Depends(get_db),
):
    items = await PaymentVerificationService(
        session, create_slip_verification_provider()
    ).list(workspace.id, payment_id, page=page, page_size=page_size)
    return success_response(
        [
            PaymentVerificationResponse.model_validate(
                item, from_attributes=True
            ).model_dump(mode="json")
            for item in items
        ]
    )
