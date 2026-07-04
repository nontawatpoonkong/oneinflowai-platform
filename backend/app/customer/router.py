"""Customer routes.

Router only handles HTTP concerns and serialization; all logic lives in
CustomerService. Every operation is scoped to the caller's current workspace.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.customer import Customer, CustomerStatus
from app.models.workspace import Workspace
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerSortField,
    CustomerUpdate,
    SortOrder,
)
from app.schemas.response import success_response
from app.services.customer import CustomerService
from app.workspace.dependencies import get_current_workspace

router = APIRouter()


def _customer_data(customer: Customer) -> dict:
    return CustomerResponse.model_validate(customer).model_dump(mode="json")


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a customer")
async def create_customer(
    payload: CustomerCreate,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    customer = await CustomerService(session).create_customer(workspace.id, payload)
    return success_response(data=_customer_data(customer), message="Customer created")


@router.get("", summary="List customers (search, filter, sort, paginate)")
async def list_customers(
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, description="Search term"),
    status_filter: CustomerStatus | None = Query(default=None, alias="status"),
    sort_by: CustomerSortField = Query(default=CustomerSortField.CREATED_AT),
    order: SortOrder = Query(default=SortOrder.DESC),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = await CustomerService(session).list_customers(
        workspace.id,
        search=q,
        status=status_filter,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if total else 0
    data = CustomerListResponse(
        items=[CustomerResponse.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
    return success_response(data=data.model_dump(mode="json"), message="OK")


@router.get("/{customer_id}", summary="Get a customer by id")
async def get_customer(
    customer_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    customer = await CustomerService(session).get_customer(workspace.id, customer_id)
    return success_response(data=_customer_data(customer), message="OK")


@router.patch("/{customer_id}", summary="Update a customer")
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    customer = await CustomerService(session).update_customer(
        workspace.id, customer_id, payload
    )
    return success_response(data=_customer_data(customer), message="Customer updated")


@router.delete("/{customer_id}", summary="Soft-delete a customer")
async def delete_customer(
    customer_id: uuid.UUID,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await CustomerService(session).delete_customer(workspace.id, customer_id)
    return success_response(data={"id": str(customer_id)}, message="Customer deleted")
