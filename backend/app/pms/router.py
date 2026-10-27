"""Workspace-scoped read-only PMS integration operations."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.integrations.pms.registry import get_pms_provider_registry
from app.models.pms import PMSEntityType, PMSIssueStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.pms import (
    PMSConnectionCreate,
    PMSConnectionPatch,
    PMSConnectionResponse,
    PMSMappingCreate,
    PMSMappingResponse,
    PMSProviderCapabilitiesResponse,
    PMSReconciliationIssueResponse,
    PMSSyncRunResponse,
)
from app.schemas.response import success_response
from app.services.pms import PMSService
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


async def _authorize(session, workspace_id, user_id, capability):
    await WorkspaceCapabilityService(session).require(workspace_id, user_id, capability)


def _connection(item):
    return PMSConnectionResponse.model_validate(item).model_dump(mode="json")


def _mapping(item):
    return PMSMappingResponse.model_validate(item).model_dump(mode="json")


def _run(item):
    return PMSSyncRunResponse.model_validate(item).model_dump(mode="json")


def _issue(item):
    return PMSReconciliationIssueResponse.model_validate(item).model_dump(mode="json")


@router.get("/providers")
async def list_providers(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_READ)
    registry = get_pms_provider_registry()
    values = []
    for name in registry.names():
        provider = registry.create(name, {})
        capabilities = PMSProviderCapabilitiesResponse.model_validate(
            provider.capabilities
        )
        values.append(
            {
                "name": name,
                "capabilities": capabilities.model_dump(mode="json"),
            }
        )
    return success_response(values)


@router.get("/connections")
async def list_connections(
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_READ)
    return success_response(
        [
            _connection(item)
            for item in await PMSService(session).list_connections(workspace.id)
        ]
    )


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: PMSConnectionCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_MANAGE)
    item = await PMSService(session).create_connection(workspace.id, payload)
    return success_response(_connection(item))


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_READ)
    return success_response(
        _connection(
            await PMSService(session).get_connection(workspace.id, connection_id)
        )
    )


@router.patch("/connections/{connection_id}")
async def update_connection(
    connection_id: uuid.UUID,
    payload: PMSConnectionPatch,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_MANAGE)
    item = await PMSService(session).update_connection(
        workspace.id, connection_id, payload
    )
    return success_response(_connection(item))


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_MANAGE)
    item = await PMSService(session).test_connection(workspace.id, connection_id)
    return success_response(_connection(item))


@router.post("/connections/{connection_id}/sync")
async def sync_connection(
    connection_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_MANAGE)
    item = await PMSService(session).sync(workspace.id, connection_id, user.id)
    return success_response(_run(item))


@router.get("/mappings")
async def list_mappings(
    connection_id: uuid.UUID | None = None,
    entity_type: PMSEntityType | None = None,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_READ)
    items = await PMSService(session).list_mappings(
        workspace.id, connection_id=connection_id, entity_type=entity_type
    )
    return success_response([_mapping(item) for item in items])


@router.post("/mappings", status_code=status.HTTP_201_CREATED)
async def create_mapping(
    payload: PMSMappingCreate,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_MANAGE)
    item = await PMSService(session).create_mapping(workspace.id, payload)
    return success_response(_mapping(item))


@router.get("/sync-runs")
async def list_sync_runs(
    connection_id: uuid.UUID | None = None,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_READ)
    items = await PMSService(session).list_runs(
        workspace.id, connection_id=connection_id
    )
    return success_response([_run(item) for item in items])


@router.get("/sync-runs/{run_id}")
async def get_sync_run(
    run_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_READ)
    return success_response(
        _run(await PMSService(session).get_run(workspace.id, run_id))
    )


@router.get("/reconciliation/issues")
async def list_reconciliation_issues(
    connection_id: uuid.UUID | None = None,
    issue_status: PMSIssueStatus | None = Query(default=None, alias="status"),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await _authorize(session, workspace.id, user.id, WorkspaceCapability.PMS_READ)
    items = await PMSService(session).list_issues(
        workspace.id, connection_id=connection_id, status=issue_status
    )
    return success_response([_issue(item) for item in items])
