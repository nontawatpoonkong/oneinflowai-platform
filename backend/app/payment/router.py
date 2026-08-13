"""Authenticated workspace-scoped customer payment routes."""

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.integrations.slip_verification import create_slip_verification_provider
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
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


def _destination(value):
    return PaymentDestinationResponse.model_validate(value).model_dump(mode="json")


def _payment(value):
    return PaymentResponse.model_validate(value).model_dump(mode="json")


@router.post("/destinations", status_code=status.HTTP_201_CREATED)
async def create_destination(
    payload: PaymentDestinationCreate,
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _payment(await PaymentService(session).create(workspace.id, payload)),
        "Payment created",
    )


@router.get("")
async def list_payments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _payment(await PaymentService(session).get(workspace.id, payment_id))
    )


@router.post("/{payment_id}/evidence", status_code=status.HTTP_201_CREATED)
async def submit_evidence(
    payment_id: uuid.UUID,
    file: UploadFile = File(...),
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
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
    workspace: Workspace = Depends(get_current_workspace),
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
