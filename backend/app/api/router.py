"""Aggregate router for versioned API routes (/api/v1)."""

from fastapi import APIRouter

from app.action.router import router as action_router
from app.action_collection.router import router as action_collection_router
from app.analytics.router import router as analytics_router
from app.auth.router import router as auth_router
from app.billing.router import router as billing_router
from app.channel.router import router as channel_router
from app.conversation.router import router as conversation_router
from app.customer.router import router as customer_router
from app.demo.router import router as demo_router
from app.knowledge.router import router as knowledge_router
from app.notification.router import router as notification_router
from app.payment.router import router as payment_router
from app.webchat.router import router as webchat_router
from app.workspace.router import router as workspace_router

api_router = APIRouter()
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(channel_router, prefix="/channels", tags=["channels"])
api_router.include_router(action_router, prefix="/actions", tags=["actions"])
api_router.include_router(
    action_collection_router,
    prefix="/action-collections",
    tags=["action-collections"],
)
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(billing_router, prefix="/billing", tags=["billing"])
api_router.include_router(workspace_router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(customer_router, prefix="/customers", tags=["customers"])
api_router.include_router(demo_router, prefix="/demo", tags=["demo"])
api_router.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(payment_router, prefix="/payments", tags=["payments"])
api_router.include_router(
    notification_router, prefix="/notifications", tags=["notifications"]
)
api_router.include_router(
    conversation_router, prefix="/conversations", tags=["conversations"]
)
api_router.include_router(webchat_router, prefix="/webchat", tags=["webchat"])
