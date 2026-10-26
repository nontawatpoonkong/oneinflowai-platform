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
from app.schemas.workspace_access import (
    AccessRequestApprove,
    AccessRequestReject,
    AccessRequestResponse,
    CapabilityRegistryResponse,
    JoinSettingsResponse,
    JoinSettingsUpdate,
    MemberCapabilitiesUpdate,
    MemberRoleUpdate,
    WorkspaceAccessResponse,
)
from app.services.account_billing import AccountBillingService
from app.services.workspace import WorkspaceService
from app.services.workspace_access import WorkspaceAccessService
from app.services.workspace_capability import WorkspaceCapabilityService

router = APIRouter()


def _workspace_data(workspace: Workspace) -> dict:
    return WorkspaceResponse.model_validate(workspace).model_dump(mode="json")


async def _member_data(
    member: WorkspaceMember, capability_service: WorkspaceCapabilityService
) -> dict:
    capabilities = await capability_service.effective_for_member(member)
    return WorkspaceMemberResponse(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        full_name=member.user.full_name,
        role=member.role,
        capabilities=sorted(capability.value for capability in capabilities),
        joined_at=member.created_at,
    ).model_dump(mode="json")


def _access_request_data(item, user=None) -> dict:
    return AccessRequestResponse(
        id=item.id,
        workspace_id=item.workspace_id,
        user_id=item.user_id,
        email=user.email if user else None,
        full_name=user.full_name if user else None,
        status=item.status,
        message=item.message,
        requested_at=item.requested_at,
        reviewed_at=item.reviewed_at,
        reviewed_by_user_id=item.reviewed_by_user_id,
        rejection_reason=item.rejection_reason,
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
    workspace = await AccountBillingService(session).provision_workspace(
        owner_user_id=user.id,
        subscription_id=payload.subscription_id,
        name=payload.name,
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


@router.get("/current/access", summary="Get effective access for a workspace")
async def current_access(
    workspace_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if workspace_id is None:
        workspace = await WorkspaceService(session).get_primary_workspace(user.id)
        workspace_id = workspace.id
    member, capabilities = await WorkspaceCapabilityService(session).effective(
        workspace_id, user.id
    )
    data = WorkspaceAccessResponse(
        workspace_id=workspace_id,
        membership_id=member.id,
        role=member.role,
        capabilities=sorted(capability.value for capability in capabilities),
    )
    return success_response(data.model_dump(mode="json"), message="OK")


@router.get("/capabilities", summary="List code-defined workspace capabilities")
async def capability_registry(
    user: User = Depends(get_current_user),
) -> dict:
    del user
    return success_response(
        CapabilityRegistryResponse(
            capabilities=WorkspaceAccessService.registry()
        ).model_dump(mode="json")
    )


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
    capability_service = WorkspaceCapabilityService(session)
    return success_response(
        data=[
            await _member_data(member, capability_service) for member in members
        ],
        message="OK",
    )


@router.get("/{workspace_id}/join-settings")
async def get_join_settings(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    setting = await WorkspaceAccessService(session).join_settings(
        workspace_id, user.id
    )
    data = JoinSettingsResponse(
        join_enabled=setting.join_enabled if setting else False,
        code_hint=setting.code_hint if setting else None,
    )
    return success_response(data.model_dump(mode="json"))


@router.post("/{workspace_id}/join-code/regenerate")
async def regenerate_join_code(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    setting, code = await WorkspaceAccessService(session).regenerate_join_code(
        workspace_id, user.id
    )
    data = JoinSettingsResponse(
        join_enabled=setting.join_enabled,
        code_hint=setting.code_hint,
        join_code=code,
    )
    return success_response(
        data.model_dump(mode="json"), "Join code regenerated; copy it now"
    )


@router.patch("/{workspace_id}/join-settings")
async def update_join_settings(
    workspace_id: uuid.UUID,
    payload: JoinSettingsUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    setting = await WorkspaceAccessService(session).set_join_enabled(
        workspace_id, user.id, payload.join_enabled
    )
    return success_response(
        JoinSettingsResponse(
            join_enabled=setting.join_enabled, code_hint=setting.code_hint
        ).model_dump(mode="json")
    )


@router.get("/{workspace_id}/access-requests")
async def list_access_requests(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    rows = await WorkspaceAccessService(session).list_requests(workspace_id, user.id)
    return success_response(
        [_access_request_data(item, request_user) for item, request_user in rows]
    )


@router.post("/{workspace_id}/access-requests/{request_id}/approve")
async def approve_access_request(
    workspace_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: AccessRequestApprove,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    member = await WorkspaceAccessService(session).approve(
        workspace_id=workspace_id,
        request_id=request_id,
        actor_user_id=user.id,
        role=payload.role,
        capability_values=payload.capabilities,
    )
    return success_response(
        await _member_data(member, WorkspaceCapabilityService(session)),
        "Workspace access approved",
    )


@router.post("/{workspace_id}/access-requests/{request_id}/reject")
async def reject_access_request(
    workspace_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: AccessRequestReject,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    item = await WorkspaceAccessService(session).reject(
        workspace_id=workspace_id,
        request_id=request_id,
        actor_user_id=user.id,
        reason=payload.reason,
    )
    return success_response(_access_request_data(item), "Workspace access rejected")


@router.patch("/{workspace_id}/members/{membership_id}")
async def update_member_role(
    workspace_id: uuid.UUID,
    membership_id: uuid.UUID,
    payload: MemberRoleUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    member = await WorkspaceAccessService(session).set_member_role(
        workspace_id, membership_id, user.id, payload.role
    )
    return success_response(
        await _member_data(member, WorkspaceCapabilityService(session)),
        "Member role updated",
    )


@router.put("/{workspace_id}/members/{membership_id}/capabilities")
async def update_member_capabilities(
    workspace_id: uuid.UUID,
    membership_id: uuid.UUID,
    payload: MemberCapabilitiesUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    capabilities = await WorkspaceAccessService(session).set_member_capabilities(
        workspace_id, membership_id, user.id, payload.capabilities
    )
    return success_response(
        {"capabilities": sorted(capability.value for capability in capabilities)},
        "Member capabilities updated",
    )


@router.delete("/{workspace_id}/members/{membership_id}")
async def remove_member(
    workspace_id: uuid.UUID,
    membership_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await WorkspaceAccessService(session).remove_member(
        workspace_id, membership_id, user.id
    )
    return success_response(message="Member removed")


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
