"""Customer repository.

All queries are workspace-scoped and exclude soft-deleted rows unless stated.
This is the only layer that touches the database for the customer domain.
"""

import uuid

from sqlalchemy import Select, func, or_, select

from app.models.customer import Customer, CustomerStatus
from app.repositories.base import BaseRepository
from app.schemas.customer import CustomerSortField, SortOrder

_SORT_COLUMNS = {
    CustomerSortField.CREATED_AT: Customer.created_at,
    CustomerSortField.UPDATED_AT: Customer.updated_at,
    CustomerSortField.DISPLAY_NAME: Customer.display_name,
}


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    def _active_in_workspace(self, workspace_id: uuid.UUID) -> Select:
        return select(Customer).where(
            Customer.workspace_id == workspace_id,
            Customer.deleted_at.is_(None),
        )

    async def get_active(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Customer | None:
        stmt = self._active_in_workspace(workspace_id).where(Customer.id == customer_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_and_count(
        self,
        workspace_id: uuid.UUID,
        *,
        search: str | None,
        status: CustomerStatus | None,
        sort_by: CustomerSortField,
        order: SortOrder,
        limit: int,
        offset: int,
    ) -> tuple[list[Customer], int]:
        stmt = self._active_in_workspace(workspace_id)

        if status is not None:
            stmt = stmt.where(Customer.status == status)

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Customer.display_name.ilike(pattern),
                    Customer.full_name.ilike(pattern),
                    Customer.phone.ilike(pattern),
                    Customer.email.ilike(pattern),
                )
            )

        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )

        sort_column = _SORT_COLUMNS[sort_by]
        stmt = stmt.order_by(
            sort_column.asc() if order == SortOrder.ASC else sort_column.desc()
        )
        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total or 0)
