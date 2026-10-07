"""Workspace-scoped persistence for authoritative Hotel data."""

import uuid
from datetime import date

from sqlalchemy import select

from app.models.hotel import InventoryDate, Property, RatePlan, RoomType
from app.repositories.base import BaseRepository


class PropertyRepository(BaseRepository[Property]):
    model = Property

    async def list(self, workspace_id):
        result = await self.session.execute(
            select(Property)
            .where(Property.workspace_id == workspace_id)
            .order_by(Property.name, Property.id)
        )
        return list(result.scalars())

    async def get(self, workspace_id, property_id):
        return await self.session.scalar(
            select(Property).where(
                Property.workspace_id == workspace_id, Property.id == property_id
            )
        )


class RoomTypeRepository(BaseRepository[RoomType]):
    model = RoomType

    async def list(self, workspace_id, property_id=None):
        stmt = select(RoomType).where(RoomType.workspace_id == workspace_id)
        if property_id:
            stmt = stmt.where(RoomType.property_id == property_id)
        result = await self.session.execute(stmt.order_by(RoomType.name, RoomType.id))
        return list(result.scalars())

    async def get(self, workspace_id, room_type_id):
        return await self.session.scalar(
            select(RoomType).where(
                RoomType.workspace_id == workspace_id, RoomType.id == room_type_id
            )
        )


class RatePlanRepository(BaseRepository[RatePlan]):
    model = RatePlan

    async def list(self, workspace_id, property_id=None, room_type_id=None):
        stmt = select(RatePlan).where(RatePlan.workspace_id == workspace_id)
        if property_id:
            stmt = stmt.where(RatePlan.property_id == property_id)
        if room_type_id:
            stmt = stmt.where(RatePlan.room_type_id == room_type_id)
        result = await self.session.execute(stmt.order_by(RatePlan.name, RatePlan.id))
        return list(result.scalars())

    async def get(self, workspace_id, rate_plan_id):
        return await self.session.scalar(
            select(RatePlan).where(
                RatePlan.workspace_id == workspace_id, RatePlan.id == rate_plan_id
            )
        )


class InventoryRepository(BaseRepository[InventoryDate]):
    model = InventoryDate

    async def get_day(self, workspace_id, room_type_id, day, *, for_update=False):
        query = select(InventoryDate).where(
            InventoryDate.workspace_id == workspace_id,
            InventoryDate.room_type_id == room_type_id,
            InventoryDate.inventory_date == day,
        )
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def list_range(
        self,
        workspace_id: uuid.UUID,
        property_id: uuid.UUID,
        start: date,
        end_exclusive: date,
    ):
        result = await self.session.execute(
            select(InventoryDate).where(
                InventoryDate.workspace_id == workspace_id,
                InventoryDate.property_id == property_id,
                InventoryDate.inventory_date >= start,
                InventoryDate.inventory_date < end_exclusive,
            )
        )
        return list(result.scalars())
