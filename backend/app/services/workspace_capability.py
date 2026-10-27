"""Authoritative role baselines plus workspace-scoped member capability grants."""

import enum
import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import WorkspaceAccessDeniedError
from app.models.workspace_access import WorkspaceMemberCapability
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.services.workspace_lifecycle import require_workspace_active


class WorkspaceCapability(enum.StrEnum):
    DASHBOARD_VIEW = "dashboard.view"
    CONVERSATION_READ = "conversation.read"
    CONVERSATION_REPLY = "conversation.reply"
    CONVERSATION_HANDOFF = "conversation.handoff"
    GUEST_READ = "guest.read"
    GUEST_NOTE = "guest.note"
    GUEST_PREFERENCE_MANAGE = "guest.preference.manage"
    GUEST_MANAGE = "guest.manage"
    BOOKING_READ = "booking.read"
    BOOKING_CREATE = "booking.create"
    BOOKING_MANAGE = "booking.manage"
    BOOKING_CANCEL = "booking.cancel"
    PROMOTION_READ = "promotion.read"
    PROMOTION_MANAGE = "promotion.manage"
    PAYMENT_READ = "payment.read"
    PAYMENT_REVIEW = "payment.review"
    ROOM_READ = "room.read"
    ROOM_MANAGE = "room.manage"
    STAY_READ = "stay.read"
    STAY_CHECKIN = "stay.checkin"
    STAY_CHECKOUT = "stay.checkout"
    STAY_NO_SHOW = "stay.no_show"
    HOUSEKEEPING_READ = "housekeeping.read"
    HOUSEKEEPING_OPERATE = "housekeeping.operate"
    HOUSEKEEPING_MANAGE = "housekeeping.manage"
    HOTEL_READINESS_OVERRIDE = "hotel.readiness.override"
    # Actions and Action Collections. Members need explicit grants; no
    # frontend preset includes these.
    ACTION_READ = "action.read"
    ACTION_OPERATE = "action.operate"
    AUTOMATION_READ = "automation.read"
    AUTOMATION_MANAGE = "automation.manage"
    PMS_READ = "pms.read"
    PMS_MANAGE = "pms.manage"
    ANALYTICS_READ = "analytics.read"
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_MANAGE = "knowledge.manage"
    WORKSPACE_MEMBERS_READ = "workspace.members.read"
    WORKSPACE_MEMBERS_MANAGE = "workspace.members.manage"
    WORKSPACE_SETTINGS_MANAGE = "workspace.settings.manage"
    WORKSPACE_BILLING_READ = "workspace.billing.read"
    AUDIT_READ = "audit.read"

    # Compatibility aliases for existing hotel-hardening call sites.
    HOTEL_HOUSEKEEPING_OPERATE = "housekeeping.operate"
    HOTEL_HOUSEKEEPING_MANAGE = "housekeeping.manage"


CAPABILITY_REGISTRY = frozenset(WorkspaceCapability)

_ROLE_CAPABILITIES = {
    WorkspaceRole.OWNER: CAPABILITY_REGISTRY,
    WorkspaceRole.ADMIN: CAPABILITY_REGISTRY,
    WorkspaceRole.MEMBER: frozenset({WorkspaceCapability.DASHBOARD_VIEW}),
}


class WorkspaceCapabilityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def membership(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember:
        await require_workspace_active(self.session, workspace_id)
        member = await self.session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if member is None:
            raise WorkspaceAccessDeniedError("Workspace membership required")
        return member

    async def effective_for_member(
        self, member: WorkspaceMember
    ) -> frozenset[WorkspaceCapability]:
        baseline = _ROLE_CAPABILITIES[member.role]
        if member.role is not WorkspaceRole.MEMBER:
            return baseline
        values = await self.session.scalars(
            select(WorkspaceMemberCapability.capability).where(
                WorkspaceMemberCapability.workspace_id == member.workspace_id,
                WorkspaceMemberCapability.membership_id == member.id,
            )
        )
        grants = {
            WorkspaceCapability(value)
            for value in values
            if value in WorkspaceCapability._value2member_map_
        }
        return frozenset(baseline | grants)

    async def effective(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[WorkspaceMember, frozenset[WorkspaceCapability]]:
        member = await self.membership(workspace_id, user_id)
        return member, await self.effective_for_member(member)

    async def require(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        capability: WorkspaceCapability,
    ) -> WorkspaceMember:
        member, capabilities = await self.effective(workspace_id, user_id)
        if capability not in capabilities:
            raise WorkspaceAccessDeniedError(
                f"Workspace capability required: {capability.value}"
            )
        return member

    async def replace_member_grants(
        self,
        *,
        workspace_id: uuid.UUID,
        membership: WorkspaceMember,
        capabilities: Iterable[WorkspaceCapability],
        granted_by_user_id: uuid.UUID,
        granted_at: datetime,
    ) -> frozenset[WorkspaceCapability]:
        if membership.workspace_id != workspace_id:
            raise WorkspaceAccessDeniedError("Membership belongs to another workspace")
        requested = frozenset(capabilities)
        await self.session.execute(
            delete(WorkspaceMemberCapability).where(
                WorkspaceMemberCapability.workspace_id == workspace_id,
                WorkspaceMemberCapability.membership_id == membership.id,
            )
        )
        if membership.role is WorkspaceRole.MEMBER:
            self.session.add_all(
                WorkspaceMemberCapability(
                    workspace_id=workspace_id,
                    membership_id=membership.id,
                    capability=capability.value,
                    granted_by_user_id=granted_by_user_id,
                    granted_at=granted_at,
                )
                for capability in sorted(requested, key=lambda item: item.value)
                if capability not in _ROLE_CAPABILITIES[WorkspaceRole.MEMBER]
            )
        await self.session.flush()
        return await self.effective_for_member(membership)

    @staticmethod
    def role_has(role: WorkspaceRole, capability: WorkspaceCapability) -> bool:
        return capability in _ROLE_CAPABILITIES[role]

    @staticmethod
    def parse_many(values: Iterable[str]) -> frozenset[WorkspaceCapability]:
        try:
            return frozenset(WorkspaceCapability(value) for value in values)
        except ValueError as exc:
            raise WorkspaceAccessDeniedError("Unknown workspace capability") from exc
