"""Workspace-admin channel connection management."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelType
from app.core.exceptions import NotFoundError, WorkspaceAccessDeniedError
from app.integrations.channels.security import ChannelCredentialCipher
from app.models.channel import ChannelConnection, ChannelConnectionStatus
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.entitlement import EntitlementService


class ChannelConnectionService:
    def __init__(self, session: AsyncSession, cipher=None) -> None:
        self.session = session
        self.cipher = cipher or ChannelCredentialCipher()

    async def require_admin(self, workspace_id, user_id) -> None:
        role = await self.session.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if role not in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
            raise WorkspaceAccessDeniedError()

    async def create(
        self,
        workspace_id,
        user_id,
        *,
        provider,
        display_name,
        external_account_id,
        external_account_name,
        credentials,
    ):
        await self.require_admin(workspace_id, user_id)
        if provider not in {ChannelType.LINE, ChannelType.FACEBOOK}:
            raise ValueError("Unsupported channel provider")
        await EntitlementService(self.session).require(
            workspace_id, f"channels.{provider.value}"
        )
        connection = ChannelConnection(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            provider=provider,
            display_name=display_name,
            external_account_id=external_account_id,
            external_account_name=external_account_name,
            status=ChannelConnectionStatus.CONNECTED,
            credential_ciphertext=b"",
            credential_nonce=b"",
            credential_key_version="",
            connected_at=datetime.now(UTC),
        )
        encrypted = self.cipher.encrypt(
            credentials,
            workspace_id=workspace_id,
            connection_id=connection.id,
            provider=provider,
        )
        connection.credential_ciphertext = encrypted.ciphertext
        connection.credential_nonce = encrypted.nonce
        connection.credential_key_version = encrypted.key_version
        self.session.add(connection)
        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    async def get_web(self, workspace_id):
        return await self.session.scalar(
            select(ChannelConnection)
            .where(
                ChannelConnection.workspace_id == workspace_id,
                ChannelConnection.provider == ChannelType.WEB,
            )
            .order_by(ChannelConnection.created_at, ChannelConnection.id)
        )

    async def connect_web(self, workspace_id, user_id):
        """Explicitly activate the credential-free WebChat connection."""
        await self.require_admin(workspace_id, user_id)
        await EntitlementService(self.session).require(workspace_id, "channels.webchat")
        # Serialize first activation as well as reconnects for this Workspace.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": workspace_id.int % (2**63)},
        )
        connection = await self.get_web(workspace_id)
        now = datetime.now(UTC)
        if connection is None:
            connection = ChannelConnection(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                provider=ChannelType.WEB,
                display_name="WebChat",
                external_account_id=str(workspace_id),
                external_account_name=None,
                status=ChannelConnectionStatus.CONNECTED,
                credential_ciphertext=b"",
                credential_nonce=b"",
                credential_key_version="none",
                connected_at=now,
            )
            self.session.add(connection)
        elif connection.status is not ChannelConnectionStatus.CONNECTED:
            connection.status = ChannelConnectionStatus.CONNECTED
            connection.connected_at = now
            connection.last_error_code = None
        else:
            return connection
        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    async def list(self, workspace_id):
        return list(
            await self.session.scalars(
                select(ChannelConnection)
                .where(ChannelConnection.workspace_id == workspace_id)
                .order_by(ChannelConnection.created_at)
            )
        )

    async def get(self, workspace_id, connection_id):
        item = await self.session.scalar(
            select(ChannelConnection).where(
                ChannelConnection.id == connection_id,
                ChannelConnection.workspace_id == workspace_id,
            )
        )
        if not item:
            raise NotFoundError("Channel connection not found")
        return item

    async def get_public(self, connection_id):
        item = await self.session.get(ChannelConnection, connection_id)
        if not item:
            raise NotFoundError("Channel connection not found")
        return item

    def credentials(self, item):
        from app.integrations.channels.security import EncryptedCredentialBundle

        return self.cipher.decrypt(
            EncryptedCredentialBundle(
                item.credential_ciphertext,
                item.credential_nonce,
                item.credential_key_version,
            ),
            workspace_id=item.workspace_id,
            connection_id=item.id,
            provider=item.provider,
        )

    async def disconnect(self, workspace_id, user_id, connection_id):
        await self.require_admin(workspace_id, user_id)
        item = await self.get(workspace_id, connection_id)
        item.status = ChannelConnectionStatus.DISCONNECTED
        await self.session.commit()
        await self.session.refresh(item)
        return item
