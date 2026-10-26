"""Workspace join, access-review, member-permission, and audit operations."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    WorkspaceAccessDeniedError,
    WorkspaceAccessRequestConflictError,
    WorkspaceJoinCodeInvalidError,
    WorkspaceNotFoundError,
    WorkspaceOwnerProtectionError,
)
from app.models.audit import AuditActorType, AuditArea
from app.models.notification import NotificationEntityType, NotificationType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_access import (
    WorkspaceAccessAuditAction,
    WorkspaceAccessAuditEvent,
    WorkspaceAccessRequest,
    WorkspaceAccessRequestStatus,
    WorkspaceJoinSetting,
    WorkspaceMemberCapability,
)
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.audit import AuditService
from app.services.notification import NotificationService
from app.services.workspace_capability import (
    CAPABILITY_REGISTRY,
    WorkspaceCapability,
    WorkspaceCapabilityService,
)

_JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_JOIN_CODE_LENGTH = 20


def normalize_join_code(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def hash_join_code(value: str) -> str:
    return hashlib.sha256(normalize_join_code(value).encode("ascii")).hexdigest()


def generate_join_code() -> str:
    raw = "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(_JOIN_CODE_LENGTH))
    return "-".join(raw[index : index + 4] for index in range(0, len(raw), 4))


class WorkspaceAccessService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.capabilities = WorkspaceCapabilityService(session)

    def _audit(
        self,
        *,
        workspace_id: uuid.UUID,
        action: WorkspaceAccessAuditAction,
        actor_user_id: uuid.UUID | None,
        target_user_id: uuid.UUID | None = None,
        access_request_id: uuid.UUID | None = None,
        membership_id: uuid.UUID | None = None,
        summary: dict | None = None,
    ) -> None:
        self.session.add(
            WorkspaceAccessAuditEvent(
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                access_request_id=access_request_id,
                membership_id=membership_id,
                action=action.value,
                summary=summary or {},
                created_at=datetime.now(UTC),
            )
        )
        AuditService(self.session).record(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            actor_type=AuditActorType.USER,
            action=action.value,
            area=AuditArea.TEAM,
            resource_type=(
                "WorkspaceMember" if membership_id else "WorkspaceAccessRequest"
            ),
            resource_id=membership_id or access_request_id,
            metadata={
                **(summary or {}),
                **({"target_user_id": str(target_user_id)} if target_user_id else {}),
            },
        )

    async def _manager(
        self, workspace_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> WorkspaceMember:
        return await self.capabilities.require(
            workspace_id,
            actor_user_id,
            WorkspaceCapability.WORKSPACE_MEMBERS_MANAGE,
        )

    async def resolve_code(self, code: str) -> Workspace:
        normalized = normalize_join_code(code)
        if len(normalized) != _JOIN_CODE_LENGTH:
            raise WorkspaceJoinCodeInvalidError()
        workspace = await self.session.scalar(
            select(Workspace)
            .join(
                WorkspaceJoinSetting,
                WorkspaceJoinSetting.workspace_id == Workspace.id,
            )
            .where(
                WorkspaceJoinSetting.join_enabled.is_(True),
                WorkspaceJoinSetting.join_code_hash == hash_join_code(normalized),
            )
        )
        if workspace is None:
            raise WorkspaceJoinCodeInvalidError()
        return workspace

    async def join_settings(
        self, workspace_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> WorkspaceJoinSetting | None:
        await self._manager(workspace_id, actor_user_id)
        return await self.session.scalar(
            select(WorkspaceJoinSetting).where(
                WorkspaceJoinSetting.workspace_id == workspace_id
            )
        )

    async def regenerate_join_code(
        self, workspace_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> tuple[WorkspaceJoinSetting, str]:
        await self._manager(workspace_id, actor_user_id)
        workspace = await self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError()
        setting = await self.session.scalar(
            select(WorkspaceJoinSetting)
            .where(WorkspaceJoinSetting.workspace_id == workspace_id)
            .with_for_update()
        )
        if setting is None:
            setting = WorkspaceJoinSetting(workspace_id=workspace_id)
            self.session.add(setting)
        code = generate_join_code()
        setting.join_code_hash = hash_join_code(code)
        setting.code_hint = normalize_join_code(code)[-4:]
        setting.join_enabled = True
        self._audit(
            workspace_id=workspace_id,
            action=WorkspaceAccessAuditAction.JOIN_CODE_REGENERATED,
            actor_user_id=actor_user_id,
            summary={"join_enabled": True},
        )
        await self.session.commit()
        await self.session.refresh(setting)
        return setting, code

    async def set_join_enabled(
        self, workspace_id: uuid.UUID, actor_user_id: uuid.UUID, enabled: bool
    ) -> WorkspaceJoinSetting:
        await self._manager(workspace_id, actor_user_id)
        setting = await self.session.scalar(
            select(WorkspaceJoinSetting)
            .where(WorkspaceJoinSetting.workspace_id == workspace_id)
            .with_for_update()
        )
        if setting is None or setting.join_code_hash is None:
            if enabled:
                raise WorkspaceAccessRequestConflictError(
                    "Generate a join code before enabling join requests"
                )
            setting = WorkspaceJoinSetting(
                workspace_id=workspace_id, join_enabled=False
            )
            self.session.add(setting)
        else:
            setting.join_enabled = enabled
        self._audit(
            workspace_id=workspace_id,
            action=WorkspaceAccessAuditAction.JOIN_REQUESTS_TOGGLED,
            actor_user_id=actor_user_id,
            summary={"join_enabled": enabled},
        )
        await self.session.commit()
        await self.session.refresh(setting)
        return setting

    async def request_access(
        self, user_id: uuid.UUID, code: str, message: str | None
    ) -> tuple[WorkspaceAccessRequest, bool]:
        workspace = await self.resolve_code(code)
        if await self.session.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == user_id,
            )
        ):
            raise WorkspaceAccessRequestConflictError(
                "User is already a member of this workspace"
            )
        existing = await self.session.scalar(
            select(WorkspaceAccessRequest).where(
                WorkspaceAccessRequest.workspace_id == workspace.id,
                WorkspaceAccessRequest.user_id == user_id,
                WorkspaceAccessRequest.status == WorkspaceAccessRequestStatus.PENDING,
            )
        )
        if existing is not None:
            return existing, False

        now = datetime.now(UTC)
        item = WorkspaceAccessRequest(
            workspace_id=workspace.id,
            user_id=user_id,
            status=WorkspaceAccessRequestStatus.PENDING,
            message=message,
            requested_at=now,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(item)
                await self.session.flush()
        except IntegrityError:
            item = await self.session.scalar(
                select(WorkspaceAccessRequest).where(
                    WorkspaceAccessRequest.workspace_id == workspace.id,
                    WorkspaceAccessRequest.user_id == user_id,
                    WorkspaceAccessRequest.status
                    == WorkspaceAccessRequestStatus.PENDING,
                )
            )
            if item is None:
                raise
            return item, False

        self._audit(
            workspace_id=workspace.id,
            action=WorkspaceAccessAuditAction.ACCESS_REQUESTED,
            actor_user_id=user_id,
            target_user_id=user_id,
            access_request_id=item.id,
        )
        recipients = await NotificationService(self.session).administrative_recipients(
            workspace.id
        )
        await NotificationService(self.session).create_for_recipients(
            workspace.id,
            recipients,
            type=NotificationType.WORKSPACE_ACCESS_REQUESTED,
            title="Workspace access request",
            body="A verified user requested access to your workspace.",
            entity_type=NotificationEntityType.WORKSPACE_ACCESS_REQUEST,
            entity_id=item.id,
            deduplication_key=f"workspace-access-request:{item.id}",
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item, True

    async def my_requests(self, user_id: uuid.UUID):
        rows = await self.session.execute(
            select(WorkspaceAccessRequest, Workspace.name)
            .join(Workspace, Workspace.id == WorkspaceAccessRequest.workspace_id)
            .where(WorkspaceAccessRequest.user_id == user_id)
            .order_by(WorkspaceAccessRequest.requested_at.desc())
        )
        return list(rows.all())

    async def cancel_request(
        self, user_id: uuid.UUID, request_id: uuid.UUID
    ) -> WorkspaceAccessRequest:
        item = await self.session.scalar(
            select(WorkspaceAccessRequest)
            .where(
                WorkspaceAccessRequest.id == request_id,
                WorkspaceAccessRequest.user_id == user_id,
            )
            .with_for_update()
        )
        if item is None:
            raise WorkspaceNotFoundError("Access request not found")
        if item.status is not WorkspaceAccessRequestStatus.PENDING:
            raise WorkspaceAccessRequestConflictError()
        item.status = WorkspaceAccessRequestStatus.CANCELLED
        item.reviewed_at = datetime.now(UTC)
        self._audit(
            workspace_id=item.workspace_id,
            action=WorkspaceAccessAuditAction.ACCESS_CANCELLED,
            actor_user_id=user_id,
            target_user_id=user_id,
            access_request_id=item.id,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def list_requests(self, workspace_id: uuid.UUID, actor_user_id: uuid.UUID):
        await self._manager(workspace_id, actor_user_id)
        rows = await self.session.execute(
            select(WorkspaceAccessRequest, User)
            .join(User, User.id == WorkspaceAccessRequest.user_id)
            .where(WorkspaceAccessRequest.workspace_id == workspace_id)
            .order_by(WorkspaceAccessRequest.requested_at.desc())
        )
        return list(rows.all())

    async def approve(
        self,
        *,
        workspace_id: uuid.UUID,
        request_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        role: WorkspaceRole,
        capability_values: list[str],
    ) -> WorkspaceMember:
        actor = await self._manager(workspace_id, actor_user_id)
        if role is WorkspaceRole.OWNER:
            raise WorkspaceOwnerProtectionError("Ownership transfer is not supported")
        # Delegated managers (ADMIN, or MEMBER granted workspace.members.manage)
        # may only add ordinary members; admin authority is OWNER-only.
        if actor.role is not WorkspaceRole.OWNER and role is not WorkspaceRole.MEMBER:
            raise WorkspaceAccessDeniedError(
                "Only workspace owners can approve admin access"
            )
        requested = self.capabilities.parse_many(capability_values)
        actor_capabilities = await self.capabilities.effective_for_member(actor)
        if not requested.issubset(actor_capabilities):
            raise WorkspaceAccessDeniedError(
                "Cannot grant capabilities you do not hold"
            )
        item = await self.session.scalar(
            select(WorkspaceAccessRequest)
            .where(
                WorkspaceAccessRequest.id == request_id,
                WorkspaceAccessRequest.workspace_id == workspace_id,
            )
            .with_for_update()
        )
        if item is None:
            raise WorkspaceNotFoundError("Access request not found")
        if item.user_id == actor_user_id:
            raise WorkspaceAccessDeniedError("Cannot approve your own access request")
        if item.status is not WorkspaceAccessRequestStatus.PENDING:
            raise WorkspaceAccessRequestConflictError()
        if await self.session.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == item.user_id,
            )
        ):
            raise WorkspaceAccessRequestConflictError("User is already a member")

        now = datetime.now(UTC)
        membership = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=item.user_id,
            role=role,
        )
        self.session.add(membership)
        await self.session.flush()
        await self.capabilities.replace_member_grants(
            workspace_id=workspace_id,
            membership=membership,
            capabilities=requested,
            granted_by_user_id=actor_user_id,
            granted_at=now,
        )
        item.status = WorkspaceAccessRequestStatus.APPROVED
        item.reviewed_at = now
        item.reviewed_by_user_id = actor_user_id
        self._audit(
            workspace_id=workspace_id,
            action=WorkspaceAccessAuditAction.ACCESS_APPROVED,
            actor_user_id=actor_user_id,
            target_user_id=item.user_id,
            access_request_id=item.id,
            membership_id=membership.id,
            summary={
                "role": role.value,
                "capabilities": sorted(capability.value for capability in requested),
            },
        )
        await self.session.commit()
        return await self.session.scalar(
            select(WorkspaceMember)
            .options(selectinload(WorkspaceMember.user))
            .where(WorkspaceMember.id == membership.id)
        )

    async def reject(
        self,
        *,
        workspace_id: uuid.UUID,
        request_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        reason: str | None,
    ) -> WorkspaceAccessRequest:
        await self._manager(workspace_id, actor_user_id)
        item = await self.session.scalar(
            select(WorkspaceAccessRequest)
            .where(
                WorkspaceAccessRequest.id == request_id,
                WorkspaceAccessRequest.workspace_id == workspace_id,
            )
            .with_for_update()
        )
        if item is None:
            raise WorkspaceNotFoundError("Access request not found")
        if item.user_id == actor_user_id:
            raise WorkspaceAccessDeniedError("Cannot review your own access request")
        if item.status is not WorkspaceAccessRequestStatus.PENDING:
            raise WorkspaceAccessRequestConflictError()
        item.status = WorkspaceAccessRequestStatus.REJECTED
        item.reviewed_at = datetime.now(UTC)
        item.reviewed_by_user_id = actor_user_id
        item.rejection_reason = reason
        self._audit(
            workspace_id=workspace_id,
            action=WorkspaceAccessAuditAction.ACCESS_REJECTED,
            actor_user_id=actor_user_id,
            target_user_id=item.user_id,
            access_request_id=item.id,
            summary={"reason_provided": bool(reason)},
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def _editable_member(
        self,
        workspace_id: uuid.UUID,
        membership_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> tuple[WorkspaceMember, WorkspaceMember]:
        actor = await self._manager(workspace_id, actor_user_id)
        target = await self.session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.id == membership_id,
                WorkspaceMember.workspace_id == workspace_id,
            )
        )
        if target is None:
            raise WorkspaceNotFoundError("Workspace membership not found")
        if target.user_id == actor_user_id:
            raise WorkspaceAccessDeniedError("Cannot change your own workspace access")
        if target.role is WorkspaceRole.OWNER:
            raise WorkspaceOwnerProtectionError()
        if (
            actor.role is not WorkspaceRole.OWNER
            and target.role is not WorkspaceRole.MEMBER
        ):
            raise WorkspaceAccessDeniedError("Only workspace owners can manage admins")
        return actor, target

    async def set_member_role(
        self,
        workspace_id: uuid.UUID,
        membership_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        role: WorkspaceRole,
    ) -> WorkspaceMember:
        actor, target = await self._editable_member(
            workspace_id, membership_id, actor_user_id
        )
        if role is WorkspaceRole.OWNER:
            raise WorkspaceOwnerProtectionError("Ownership transfer is not supported")
        if actor.role is not WorkspaceRole.OWNER and role is not WorkspaceRole.MEMBER:
            raise WorkspaceAccessDeniedError(
                "Only workspace owners can grant admin access"
            )
        target.role = role
        if role is not WorkspaceRole.MEMBER:
            await self.session.execute(
                delete(WorkspaceMemberCapability).where(
                    WorkspaceMemberCapability.membership_id == target.id
                )
            )
        self._audit(
            workspace_id=workspace_id,
            action=WorkspaceAccessAuditAction.MEMBER_ROLE_CHANGED,
            actor_user_id=actor_user_id,
            target_user_id=target.user_id,
            membership_id=target.id,
            summary={"role": role.value},
        )
        await self.session.commit()
        return await self.session.scalar(
            select(WorkspaceMember)
            .options(selectinload(WorkspaceMember.user))
            .where(WorkspaceMember.id == target.id)
        )

    async def set_member_capabilities(
        self,
        workspace_id: uuid.UUID,
        membership_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        capability_values: list[str],
    ) -> frozenset[WorkspaceCapability]:
        actor, target = await self._editable_member(
            workspace_id, membership_id, actor_user_id
        )
        if target.role is not WorkspaceRole.MEMBER:
            raise WorkspaceAccessDeniedError(
                "Owner and admin authority comes from role baseline"
            )
        requested = self.capabilities.parse_many(capability_values)
        actor_capabilities = await self.capabilities.effective_for_member(actor)
        if not requested.issubset(actor_capabilities):
            raise WorkspaceAccessDeniedError(
                "Cannot grant capabilities you do not hold"
            )
        effective = await self.capabilities.replace_member_grants(
            workspace_id=workspace_id,
            membership=target,
            capabilities=requested,
            granted_by_user_id=actor_user_id,
            granted_at=datetime.now(UTC),
        )
        self._audit(
            workspace_id=workspace_id,
            action=WorkspaceAccessAuditAction.MEMBER_CAPABILITIES_CHANGED,
            actor_user_id=actor_user_id,
            target_user_id=target.user_id,
            membership_id=target.id,
            summary={
                "capabilities": sorted(capability.value for capability in requested)
            },
        )
        await self.session.commit()
        return effective

    async def remove_member(
        self,
        workspace_id: uuid.UUID,
        membership_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> None:
        _, target = await self._editable_member(
            workspace_id, membership_id, actor_user_id
        )
        self._audit(
            workspace_id=workspace_id,
            action=WorkspaceAccessAuditAction.MEMBER_REMOVED,
            actor_user_id=actor_user_id,
            target_user_id=target.user_id,
            membership_id=target.id,
            summary={"role": target.role.value},
        )
        await self.session.delete(target)
        await self.session.commit()

    @staticmethod
    def registry() -> list[str]:
        return sorted(capability.value for capability in CAPABILITY_REGISTRY)
