"""Customer service.

Business logic for the customer domain. All operations are scoped to a
workspace_id supplied by the caller (resolved from the authenticated user's
current workspace), enforcing workspace isolation.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.customer import Customer, CustomerStatus
from app.repositories.customer import CustomerRepository
from app.schemas.customer import (
    CustomerCreate,
    CustomerSortField,
    CustomerUpdate,
    SortOrder,
)


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.customers = CustomerRepository(session)

    async def create_customer(
        self, workspace_id: uuid.UUID, data: CustomerCreate
    ) -> Customer:
        customer = Customer(workspace_id=workspace_id, **data.model_dump())
        await self.customers.add(customer)
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def get_customer(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Customer:
        customer = await self.customers.get_active(workspace_id, customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    async def list_customers(
        self,
        workspace_id: uuid.UUID,
        *,
        search: str | None,
        status: CustomerStatus | None,
        sort_by: CustomerSortField,
        order: SortOrder,
        page: int,
        page_size: int,
    ) -> tuple[list[Customer], int]:
        offset = (page - 1) * page_size
        return await self.customers.list_and_count(
            workspace_id,
            search=search,
            status=status,
            sort_by=sort_by,
            order=order,
            limit=page_size,
            offset=offset,
        )

    async def update_customer(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        data: CustomerUpdate,
    ) -> Customer:
        customer = await self.get_customer(workspace_id, customer_id)
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(customer, field, value)
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def delete_customer(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID
    ) -> None:
        """Soft delete: mark deleted_at; row is retained."""
        customer = await self.get_customer(workspace_id, customer_id)
        customer.deleted_at = datetime.now(UTC)
        await self.session.commit()
