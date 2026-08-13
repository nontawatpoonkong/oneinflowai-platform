"""Workspace routes.

Router contains no business logic — it delegates to WorkspaceService and
serializes results into the standard response envelope.

NOTE: The standalone "Create Workspace" endpoint (POST) is part of the overall
Sprint 1 scope; it is retained here (flagged in an earlier step).
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.response import success_response
from app.schemas.workspace import (
    WorkspaceAIInstructionsResponse,
    WorkspaceAIInstructionsUpdate,
    WorkspaceCreateRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from app.services.workspace import WorkspaceService

router = APIRouter()


def _workspace_data(workspace: Workspace) -> dict:
    return WorkspaceResponse.model_validate(workspace).model_dump(mode="json")


def _member_data(member: WorkspaceMember) -> dict:
    return WorkspaceMemberResponse(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        full_name=member.user.full_name,
        role=member.role,
        joined_at=member.created_at,
    ).model_dump(mode="json")


@router.get("", summary="List workspaces the current user belongs to")
async def list_workspaces(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    workspaces = await WorkspaceService(session).list_for_user(user.id)
    return success_response(
        data=[_workspace_data(ws) for ws in workspaces], message="OK"
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a workspace")
async def create_workspace(
    payload: WorkspaceCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    workspace = await WorkspaceService(session).create_workspace(
        owner_id=user.id, name=payload.name
    )
    return success_response(
        data=_workspace_data(workspace), message="Workspace created"
    )


@router.get("/me", summary="Get the current user's primary workspace")
async def get_my_workspace(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    workspace = await WorkspaceService(session).get_primary_workspace(user.id)
    return success_response(data=_workspace_data(workspace), message="OK")


@router.get(
    "/{workspace_id}/ai-instructions", summary="Get Workspace AI instructions"
)
async def get_ai_instructions(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    instructions = await WorkspaceService(session).get_ai_instructions(
        workspace_id, user.id
    )
    data = WorkspaceAIInstructionsResponse(instructions=instructions)
    return success_response(data=data.model_dump(), message="OK")


@router.put(
    "/{workspace_id}/ai-instructions", summary="Update Workspace AI instructions"
)
async def update_ai_instructions(
    workspace_id: uuid.UUID,
    payload: WorkspaceAIInstructionsUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = WorkspaceService(session)
    instructions = await service.update_ai_instructions(
        workspace_id, user.id, payload.instructions
    )
    data = WorkspaceAIInstructionsResponse(instructions=instructions)
    return success_response(data=data.model_dump(), message="AI instructions updated")


@router.get("/{slug}", summary="Public workspace lookup by slug")
async def get_workspace_by_slug(
    slug: str, session: AsyncSession = Depends(get_db)
) -> dict:
    workspace = await WorkspaceService(session).get_by_slug(slug)
    return success_response(data=_workspace_data(workspace), message="OK")


@router.get(
    "/{workspace_id}/members", summary="List workspace members with their roles"
)
async def list_workspace_members(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    members = await WorkspaceService(session).list_members(workspace_id, user.id)
    return success_response(
        data=[_member_data(member) for member in members], message="OK"
    )


@router.patch("/{workspace_id}", summary="Update a workspace (owner only)")
async def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    workspace = await WorkspaceService(session).update_workspace(
        workspace_id, user.id, payload.name
    )
    return success_response(
        data=_workspace_data(workspace), message="Workspace updated"
    )
