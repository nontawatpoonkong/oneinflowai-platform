"""Aggregate router for versioned API routes (/api/v1)."""

from fastapi import APIRouter

from app.auth.router import router as auth_router
from app.conversation.router import router as conversation_router
from app.customer.router import router as customer_router
from app.workspace.router import router as workspace_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(workspace_router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(customer_router, prefix="/customers", tags=["customers"])
api_router.include_router(
    conversation_router, prefix="/conversations", tags=["conversations"]
)
