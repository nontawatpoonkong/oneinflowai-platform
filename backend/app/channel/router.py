"""Channel configuration and authenticated provider webhooks."""

import json
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.channels import ChannelType
from app.core.config import get_settings
from app.core.exceptions import AppError, AuthenticationError
from app.database.session import get_db
from app.integrations.channels.facebook import FacebookMessengerChannelProvider
from app.integrations.channels.line import LineChannelProvider
from app.models.channel import ChannelConnectionStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.channel import (
    ChannelConnectionResponse,
    FacebookConnectionCreate,
    LineConnectionCreate,
)
from app.schemas.response import success_response
from app.services.channel_connection import ChannelConnectionService
from app.services.channel_ingestion import (
    ChannelInboundUnavailableError,
    ChannelMessageIngestionService,
)
from app.services.workspace_capability import WorkspaceCapability
from app.services.workspace_lifecycle import require_workspace_active
from app.workspace.dependencies import require_workspace_capability

router = APIRouter()

_channel_manage = require_workspace_capability(
    WorkspaceCapability.WORKSPACE_SETTINGS_MANAGE
)


class InvalidWebhookError(AppError):
    status_code = 401
    code = "INVALID_WEBHOOK_SIGNATURE"
    message = "Invalid webhook signature"


def _data(item):
    return ChannelConnectionResponse.model_validate(item).model_dump(mode="json")


@router.get("")
async def list_connections(
    workspace: Workspace = Depends(_channel_manage),
    session: AsyncSession = Depends(get_db),
):
    items = await ChannelConnectionService(session).list(workspace.id)
    return success_response([_data(item) for item in items])


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: uuid.UUID,
    workspace: Workspace = Depends(_channel_manage),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _data(await ChannelConnectionService(session).get(workspace.id, connection_id))
    )


@router.post("/line", status_code=status.HTTP_201_CREATED)
async def create_line(
    payload: LineConnectionCreate,
    workspace: Workspace = Depends(_channel_manage),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    item = await ChannelConnectionService(session).create(
        workspace.id,
        user.id,
        provider=ChannelType.LINE,
        display_name=payload.display_name,
        external_account_id=payload.external_account_id,
        external_account_name=payload.external_account_name,
        credentials={
            "channel_access_token": payload.channel_access_token,
            "channel_secret": payload.channel_secret,
        },
    )
    return success_response(_data(item))


@router.post("/webchat")
async def connect_webchat(
    workspace: Workspace = Depends(_channel_manage),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    item = await ChannelConnectionService(session).connect_web(workspace.id, user.id)
    return success_response(_data(item))


@router.post("/facebook", status_code=status.HTTP_201_CREATED)
async def create_facebook(
    payload: FacebookConnectionCreate,
    workspace: Workspace = Depends(_channel_manage),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    item = await ChannelConnectionService(session).create(
        workspace.id,
        user.id,
        provider=ChannelType.FACEBOOK,
        display_name=payload.display_name,
        external_account_id=payload.external_account_id,
        external_account_name=payload.external_account_name,
        credentials={
            "page_access_token": payload.page_access_token,
            "app_secret": payload.app_secret,
            "verify_token": payload.verify_token,
        },
    )
    return success_response(_data(item))


@router.delete("/connections/{connection_id}")
async def disconnect(
    connection_id: uuid.UUID,
    workspace: Workspace = Depends(_channel_manage),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return success_response(
        _data(
            await ChannelConnectionService(session).disconnect(
                workspace.id, user.id, connection_id
            )
        )
    )


async def _body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > get_settings().CHANNEL_WEBHOOK_MAX_BYTES:
        raise AppError("Webhook payload is too large")
    return body


async def _process(connection_id, body, signature, request, session, provider_cls):
    connections = ChannelConnectionService(session)
    connection = await connections.get_public(connection_id)
    await require_workspace_active(session, connection.workspace_id)
    if connection.status is not ChannelConnectionStatus.CONNECTED:
        raise AuthenticationError("Channel connection is inactive")
    provider = provider_cls(
        connections.credentials(connection),
        timeout=get_settings().CHANNEL_PROVIDER_TIMEOUT_SECONDS,
    )
    if not provider.verify_signature(body, signature):
        raise InvalidWebhookError()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AppError("Malformed webhook payload") from exc
    if not isinstance(payload, dict):
        raise AppError("Malformed webhook payload")
    ingestion = ChannelMessageIngestionService(session, request.app.state.qdrant)
    for inbound in provider.parse(payload):
        if inbound.provider is not connection.provider:
            raise InvalidWebhookError()
        try:
            await ingestion.process(connection, inbound)
        except ChannelInboundUnavailableError as exc:
            raise AuthenticationError("Channel connection is inactive") from exc
    return success_response({"accepted": True})


@router.post("/webhooks/line/{connection_id}")
async def line_webhook(
    connection_id: uuid.UUID,
    request: Request,
    x_line_signature: str = Header(alias="X-Line-Signature"),
    session: AsyncSession = Depends(get_db),
):
    return await _process(
        connection_id,
        await _body(request),
        x_line_signature,
        request,
        session,
        LineChannelProvider,
    )


@router.get("/webhooks/facebook/{connection_id}")
async def facebook_verify(
    connection_id: uuid.UUID,
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
    session: AsyncSession = Depends(get_db),
):
    connections = ChannelConnectionService(session)
    connection = await connections.get_public(connection_id)
    await require_workspace_active(session, connection.workspace_id)
    provider = FacebookMessengerChannelProvider(
        connections.credentials(connection),
        timeout=get_settings().CHANNEL_PROVIDER_TIMEOUT_SECONDS,
    )
    if hub_mode != "subscribe" or not provider.verify_token(hub_verify_token):
        raise InvalidWebhookError()
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/webhooks/facebook/{connection_id}")
async def facebook_webhook(
    connection_id: uuid.UUID,
    request: Request,
    x_hub_signature_256: str = Header(alias="X-Hub-Signature-256"),
    session: AsyncSession = Depends(get_db),
):
    return await _process(
        connection_id,
        await _body(request),
        x_hub_signature_256,
        request,
        session,
        FacebookMessengerChannelProvider,
    )
