"""Trusted OneInFlowAI platform billing administration."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.billing import SubscriptionActivationRequest
from app.schemas.response import success_response
from app.services.account_billing import AccountBillingService

router = APIRouter()


@router.post("/subscriptions/{subscription_id}/activate")
async def activate_subscription(
    subscription_id: uuid.UUID,
    payload: SubscriptionActivationRequest,
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    subscription = await AccountBillingService(session).activate_subscription(
        actor=actor,
        subscription_id=subscription_id,
        target_status=payload.status,
        reason=payload.reason,
    )
    return success_response(
        {
            "id": str(subscription.id),
            "status": subscription.status.value,
            "current_period_start": subscription.current_period_start.isoformat(),
            "current_period_end": subscription.current_period_end.isoformat(),
        },
        message="Subscription activated",
    )
