"""Customer service.

Business logic for the customer domain. All operations are scoped to a
workspace_id supplied by the caller (resolved from the authenticated user's
current workspace), enforcing workspace isolation.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.audit import AuditActorType, AuditArea
from app.models.customer import Customer, CustomerStatus
from app.repositories.customer import CustomerRepository
from app.schemas.customer import (
    CustomerCreate,
    CustomerSortField,
    CustomerUpdate,
    SortOrder,
)
from app.services.audit import AuditService


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.customers = CustomerRepository(session)

    async def create_customer(
        self,
        workspace_id: uuid.UUID,
        data: CustomerCreate,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> Customer:
        customer = Customer(workspace_id=workspace_id, **data.model_dump())
        await self.customers.add(customer)
        if actor_user_id is not None:
            self._audit(
                customer,
                actor_user_id,
                "CUSTOMER_CREATED",
                {"provided_fields": sorted(data.model_dump(exclude_unset=True))},
            )
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
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> Customer:
        customer = await self.get_customer(workspace_id, customer_id)
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(customer, field, value)
        if actor_user_id is not None:
            self._audit(
                customer,
                actor_user_id,
                "CUSTOMER_UPDATED",
                {"changed_fields": sorted(changes)},
            )
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def delete_customer(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        """Soft delete: mark deleted_at; row is retained."""
        customer = await self.get_customer(workspace_id, customer_id)
        customer.deleted_at = datetime.now(UTC)
        if actor_user_id is not None:
            self._audit(customer, actor_user_id, "CUSTOMER_DELETED", {})
        await self.session.commit()

    def _audit(
        self, customer: Customer, actor_user_id: uuid.UUID, action: str, metadata
    ) -> None:
        # Field names only: guest names, contact details, and notes stay out of
        # the audit trail.
        AuditService(self.session).record(
            workspace_id=customer.workspace_id,
            actor_user_id=actor_user_id,
            actor_type=AuditActorType.USER,
            action=action,
            area=AuditArea.GUESTS,
            resource_type="Customer",
            resource_id=customer.id,
            metadata=metadata,
        )
