from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.crm.models import Customer, CustomerAddress
from app.modules.crm.schemas import (
    CustomerAddressCreate,
    CustomerAddressResponse,
    CustomerAddressUpdate,
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
    PaginatedCustomersResponse,
)
from app.modules.crm.service import CustomerService
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User

router = APIRouter(prefix="", tags=["CRM - Customers"])


def get_crm_service(db: Annotated[Session, Depends(get_db)]) -> CustomerService:
    return CustomerService(db)


@router.get("/customers", response_model=PaginatedCustomersResponse)
def list_customers(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerService, Depends(get_crm_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: str | None = Query(None),
    search: str | None = Query(None),
    owner_user_id: int | None = Query(None),
) -> PaginatedCustomersResponse:
    customers, total = service.list_customers(
        page=page, page_size=page_size, status=status, search=search, owner_user_id=owner_user_id
    )
    return PaginatedCustomersResponse(
        items=[CustomerResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerService, Depends(get_crm_service)],
) -> Customer:
    return service.get_customer(customer_id)


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerService, Depends(get_crm_service)],
) -> Customer:
    return service.create_customer(payload, creator_id=current_user.id)


@router.patch("/customers/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerService, Depends(get_crm_service)],
) -> Customer:
    return service.update_customer(customer_id, payload, updater_id=current_user.id)


@router.post("/customers/{customer_id}/deactivate", response_model=CustomerResponse)
def deactivate_customer(
    customer_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerService, Depends(get_crm_service)],
) -> Customer:
    return service.deactivate_customer(customer_id, updater_id=current_user.id)


@router.post(
    "/customers/{customer_id}/addresses",
    response_model=CustomerAddressResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_customer_address(
    customer_id: int,
    payload: CustomerAddressCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerService, Depends(get_crm_service)],
) -> CustomerAddress:
    return service.add_address(customer_id, payload, creator_id=current_user.id)


@router.patch("/customers/addresses/{address_id}", response_model=CustomerAddressResponse)
def update_customer_address(
    address_id: int,
    payload: CustomerAddressUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerService, Depends(get_crm_service)],
) -> CustomerAddress:
    return service.update_address(address_id, payload, updater_id=current_user.id)
