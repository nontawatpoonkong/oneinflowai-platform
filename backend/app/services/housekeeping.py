"""Transactional housekeeping lifecycle, capabilities, and overrides."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, WorkspaceAccessDeniedError
from app.models.audit import AuditActorType, AuditArea
from app.models.hotel import Property, RoomType
from app.models.housekeeping import (
    HousekeepingEvent,
    HousekeepingEventType,
    HousekeepingPriority,
    HousekeepingTask,
    HousekeepingTaskStatus,
    RoomReadinessOverrideEvent,
)
from app.models.stay import (
    HotelRoom,
    RoomOperationalStatus,
    RoomReadinessStatus,
    Stay,
)
from app.models.workspace_member import WorkspaceMember
from app.schemas.housekeeping import (
    HousekeepingEventResponse,
    HousekeepingTaskListResponse,
    HousekeepingTaskResponse,
    RoomReadinessOverrideEventResponse,
    RoomReadinessOverrideResponse,
)
from app.services.audit import AuditService
from app.services.automation_events import emit_housekeeping_event
from app.services.stay import StayConflictError, StayTransitionError
from app.services.workspace_capability import (
    WorkspaceCapability,
    WorkspaceCapabilityService,
)


class HousekeepingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.capabilities = WorkspaceCapabilityService(session)

    async def list_tasks(
        self,
        workspace_id,
        *,
        property_id=None,
        room_id=None,
        status=None,
        assignee_id=None,
        priority=None,
        readiness_status=None,
        page=1,
        page_size=50,
    ):
        query = self._base_query().where(HousekeepingTask.workspace_id == workspace_id)
        for condition in (
            HousekeepingTask.property_id == property_id if property_id else None,
            HousekeepingTask.room_id == room_id if room_id else None,
            HousekeepingTask.status == status if status else None,
            HousekeepingTask.assigned_to_user_id == assignee_id
            if assignee_id
            else None,
            HousekeepingTask.priority == priority if priority else None,
            HotelRoom.readiness_status == readiness_status
            if readiness_status
            else None,
        ):
            if condition is not None:
                query = query.where(condition)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                query.order_by(HousekeepingTask.created_at, HousekeepingTask.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return HousekeepingTaskListResponse(
            items=[self._response(*row, events=[]) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    async def get_task(self, workspace_id, task_id):
        row = (
            await self.session.execute(
                self._base_query().where(
                    HousekeepingTask.workspace_id == workspace_id,
                    HousekeepingTask.id == task_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Housekeeping task not found")
        events = list(
            (
                await self.session.scalars(
                    select(HousekeepingEvent)
                    .where(
                        HousekeepingEvent.workspace_id == workspace_id,
                        HousekeepingEvent.task_id == task_id,
                    )
                    .order_by(HousekeepingEvent.sequence)
                    .limit(500)
                )
            ).all()
        )
        return self._response(
            *row,
            events=[HousekeepingEventResponse.model_validate(item) for item in events],
        )

    async def assign(self, workspace_id, task_id, assignee_id, actor_id):
        await self.capabilities.require(
            workspace_id,
            actor_id,
            WorkspaceCapability.HOTEL_HOUSEKEEPING_MANAGE,
        )
        member = await self.session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == assignee_id,
            )
        )
        if member is None:
            raise StayConflictError("Assignee must belong to this workspace")
        task = await self._task(workspace_id, task_id, lock=True)
        if task.status not in {
            HousekeepingTaskStatus.PENDING,
            HousekeepingTaskStatus.IN_PROGRESS,
        }:
            raise StayTransitionError("Completed or cancelled task cannot be assigned")
        if task.assigned_to_user_id == assignee_id:
            await self.session.commit()
            return await self.get_task(workspace_id, task_id)
        task.assigned_to_user_id = assignee_id
        self._event(task, HousekeepingEventType.HOUSEKEEPING_ASSIGNED, actor_id)
        await self.session.commit()
        return await self.get_task(workspace_id, task_id)

    async def start(self, workspace_id, task_id, actor_id):
        task = await self._task(workspace_id, task_id, lock=True)
        await self._require_actor(workspace_id, task, actor_id)
        if task.status == HousekeepingTaskStatus.IN_PROGRESS:
            await self.session.commit()
            return await self.get_task(workspace_id, task_id)
        if task.status != HousekeepingTaskStatus.PENDING:
            raise StayTransitionError("Only a pending housekeeping task can start")
        room = await self._room(workspace_id, task.room_id, lock=True)
        if room.readiness_status != RoomReadinessStatus.DIRTY:
            raise StayConflictError("Room must be dirty before cleaning starts")
        task.status = HousekeepingTaskStatus.IN_PROGRESS
        task.started_at = datetime.now(UTC)
        room.readiness_status = RoomReadinessStatus.CLEANING
        self._event(task, HousekeepingEventType.HOUSEKEEPING_STARTED, actor_id)
        await self.session.commit()
        return await self.get_task(workspace_id, task_id)

    async def complete(self, workspace_id, task_id, actor_id):
        task = await self._task(workspace_id, task_id, lock=True)
        await self._require_actor(workspace_id, task, actor_id)
        if task.status == HousekeepingTaskStatus.COMPLETED:
            await self.session.commit()
            return await self.get_task(workspace_id, task_id)
        if task.status != HousekeepingTaskStatus.IN_PROGRESS:
            raise StayTransitionError("Only cleaning in progress can complete")
        room = await self._room(workspace_id, task.room_id, lock=True)
        if room.readiness_status != RoomReadinessStatus.CLEANING:
            raise StayConflictError("Room readiness is inconsistent")
        task.status = HousekeepingTaskStatus.COMPLETED
        task.completed_at = datetime.now(UTC)
        room.readiness_status = RoomReadinessStatus.READY
        self._event(task, HousekeepingEventType.HOUSEKEEPING_COMPLETED, actor_id)
        self._event(task, HousekeepingEventType.ROOM_READY, actor_id)
        await emit_housekeeping_event(
            self.session, task, "hotel.housekeeping.completed"
        )
        await emit_housekeeping_event(self.session, task, "hotel.room.ready")
        await self.session.commit()
        return await self.get_task(workspace_id, task_id)

    async def cancel(self, workspace_id, task_id, actor_id):
        await self.capabilities.require(
            workspace_id,
            actor_id,
            WorkspaceCapability.HOTEL_HOUSEKEEPING_MANAGE,
        )
        task = await self._task(workspace_id, task_id, lock=True)
        if task.status == HousekeepingTaskStatus.CANCELLED:
            await self.session.commit()
            return await self.get_task(workspace_id, task_id)
        if task.status == HousekeepingTaskStatus.COMPLETED:
            raise StayTransitionError("Completed housekeeping cannot be cancelled")
        room = await self._room(workspace_id, task.room_id, lock=True)
        task.status = HousekeepingTaskStatus.CANCELLED
        if room.readiness_status == RoomReadinessStatus.CLEANING:
            room.readiness_status = RoomReadinessStatus.DIRTY
        self._event(task, HousekeepingEventType.HOUSEKEEPING_CANCELLED, actor_id)
        await self.session.commit()
        return await self.get_task(workspace_id, task_id)

    async def override_readiness(
        self,
        workspace_id: uuid.UUID,
        room_id: uuid.UUID,
        new_readiness: RoomReadinessStatus,
        reason: str,
        actor_id: uuid.UUID,
    ) -> RoomReadinessOverrideResponse:
        await self.capabilities.require(
            workspace_id,
            actor_id,
            WorkspaceCapability.HOTEL_READINESS_OVERRIDE,
        )
        if new_readiness == RoomReadinessStatus.CLEANING:
            raise StayTransitionError(
                "CLEANING readiness can only be entered by starting a task"
            )

        active_task = await self._active_task(workspace_id, room_id, lock=True)
        room = await self._room(workspace_id, room_id, lock=True)
        if active_task is None:
            active_task = await self._active_task(workspace_id, room_id, lock=True)
        previous = room.readiness_status
        if room.operational_status == RoomOperationalStatus.OCCUPIED:
            raise StayConflictError("An occupied room readiness cannot be overridden")
        if previous == new_readiness:
            raise StayTransitionError("Readiness override must change the room state")

        if active_task is not None:
            active_task.status = HousekeepingTaskStatus.CANCELLED
            self._event(
                active_task,
                HousekeepingEventType.HOUSEKEEPING_CANCELLED,
                actor_id,
                metadata={"source": "READINESS_OVERRIDE"},
            )
            await self.session.flush()

        if new_readiness == RoomReadinessStatus.DIRTY:
            replacement = HousekeepingTask(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                property_id=room.property_id,
                room_id=room.id,
                stay_id=None,
                status=HousekeepingTaskStatus.PENDING,
                priority=HousekeepingPriority.NORMAL,
                created_by_user_id=actor_id,
                source="READINESS_OVERRIDE",
            )
            self.session.add(replacement)
            await self.session.flush()
            self._event(
                replacement,
                HousekeepingEventType.HOUSEKEEPING_TASK_CREATED,
                actor_id,
                metadata={"source": "READINESS_OVERRIDE"},
            )

        room.readiness_status = new_readiness
        event = RoomReadinessOverrideEvent(
            workspace_id=workspace_id,
            property_id=room.property_id,
            room_id=room.id,
            actor_user_id=actor_id,
            previous_readiness=previous.value,
            new_readiness=new_readiness.value,
            reason=reason,
        )
        self.session.add(event)
        AuditService(self.session).record(
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            actor_type=AuditActorType.USER,
            action="ROOM_READINESS_OVERRIDDEN",
            area=AuditArea.HOUSEKEEPING,
            resource_type="HotelRoom",
            resource_id=room.id,
            metadata={
                "previous_readiness": previous.value,
                "new_readiness": new_readiness.value,
            },
        )
        await self.session.commit()
        await self.session.refresh(event)
        return RoomReadinessOverrideResponse(
            room_id=room.id,
            operational_status=room.operational_status,
            readiness_status=room.readiness_status,
            event=RoomReadinessOverrideEventResponse.model_validate(event),
        )

    def _base_query(self):
        return (
            select(
                HousekeepingTask,
                HotelRoom,
                Property.name,
                RoomType.name,
                Stay.actual_check_out_at,
            )
            .join(
                HotelRoom,
                (HotelRoom.id == HousekeepingTask.room_id)
                & (HotelRoom.workspace_id == HousekeepingTask.workspace_id),
            )
            .join(
                Property,
                (Property.id == HousekeepingTask.property_id)
                & (Property.workspace_id == HousekeepingTask.workspace_id),
            )
            .join(
                RoomType,
                (RoomType.id == HotelRoom.room_type_id)
                & (RoomType.workspace_id == HousekeepingTask.workspace_id),
            )
            .outerjoin(
                Stay,
                (Stay.id == HousekeepingTask.stay_id)
                & (Stay.workspace_id == HousekeepingTask.workspace_id),
            )
        )

    async def _task(self, workspace_id, task_id, *, lock=False):
        query = select(HousekeepingTask).where(
            HousekeepingTask.workspace_id == workspace_id,
            HousekeepingTask.id == task_id,
        )
        if lock:
            query = query.with_for_update()
        task = await self.session.scalar(query)
        if task is None:
            raise NotFoundError("Housekeeping task not found")
        return task

    async def _room(self, workspace_id, room_id, *, lock=False):
        query = select(HotelRoom).where(
            HotelRoom.workspace_id == workspace_id, HotelRoom.id == room_id
        )
        if lock:
            query = query.with_for_update()
        room = await self.session.scalar(query)
        if room is None:
            raise NotFoundError("Hotel room not found")
        return room

    async def _active_task(self, workspace_id, room_id, *, lock=False):
        query = select(HousekeepingTask).where(
            HousekeepingTask.workspace_id == workspace_id,
            HousekeepingTask.room_id == room_id,
            HousekeepingTask.status.in_(
                (HousekeepingTaskStatus.PENDING, HousekeepingTaskStatus.IN_PROGRESS)
            ),
        )
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def _require_actor(self, workspace_id, task, user_id):
        member = await self.capabilities.require(
            workspace_id,
            user_id,
            WorkspaceCapability.HOTEL_HOUSEKEEPING_OPERATE,
        )
        if (
            not self.capabilities.role_has(
                member.role, WorkspaceCapability.HOTEL_HOUSEKEEPING_MANAGE
            )
            and task.assigned_to_user_id != user_id
        ):
            raise WorkspaceAccessDeniedError(
                "Housekeeping task must be assigned to this member"
            )

    def _event(self, task, event_type, actor_id, *, metadata=None):
        self.session.add(
            HousekeepingEvent(
                workspace_id=task.workspace_id,
                property_id=task.property_id,
                task_id=task.id,
                room_id=task.room_id,
                event_type=event_type,
                actor_user_id=actor_id,
                event_metadata=metadata or {},
            )
        )
        AuditService(self.session).record(
            workspace_id=task.workspace_id,
            actor_user_id=actor_id,
            actor_type=(AuditActorType.USER if actor_id else AuditActorType.SYSTEM),
            action=event_type.value,
            area=AuditArea.HOUSEKEEPING,
            resource_type="HousekeepingTask",
            resource_id=task.id,
            metadata={"room_id": str(task.room_id), **(metadata or {})},
        )

    @staticmethod
    def _response(task, room, property_name, room_type_name, checkout_at, *, events):
        return HousekeepingTaskResponse(
            id=task.id,
            workspace_id=task.workspace_id,
            property_id=task.property_id,
            property_name=property_name,
            room_id=task.room_id,
            room_code=room.code,
            room_type_name=room_type_name,
            stay_id=task.stay_id,
            status=task.status,
            priority=task.priority,
            assigned_to_user_id=task.assigned_to_user_id,
            source=task.source,
            operational_status=room.operational_status,
            readiness_status=room.readiness_status,
            checkout_at=checkout_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
            events=events,
        )
