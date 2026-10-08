from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.identity.dependencies import get_current_user, require_superuser
from app.modules.identity.models import User
from app.modules.organization.models import CompanySettings, Department, Employee
from app.modules.organization.schemas import (
    CompanySettingsResponse,
    CompanySettingsUpdate,
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
    PaginatedEmployeesResponse,
)
from app.modules.organization.service import OrganizationService

router = APIRouter(prefix="", tags=["Organization"])


def get_org_service(db: Annotated[Session, Depends(get_db)]) -> OrganizationService:
    return OrganizationService(db)


# --- Company Settings ---
@router.get("/company-settings", response_model=CompanySettingsResponse)
def get_company_settings(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
) -> CompanySettings:
    return service.get_or_create_settings()


@router.put("/company-settings", response_model=CompanySettingsResponse)
def update_company_settings(
    payload: CompanySettingsUpdate,
    current_user: Annotated[User, Depends(require_superuser)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
) -> CompanySettings:
    return service.update_settings(payload, updater_id=current_user.id)


# --- Departments ---
@router.get("/departments", response_model=list[DepartmentResponse])
def list_departments(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
    include_inactive: bool = Query(False),
) -> list[Department]:
    return service.list_departments(include_inactive=include_inactive)


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    current_user: Annotated[User, Depends(require_superuser)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
) -> Department:
    return service.create_department(payload, creator_id=current_user.id)


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
def update_department(
    department_id: int,
    payload: DepartmentUpdate,
    current_user: Annotated[User, Depends(require_superuser)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
) -> Department:
    return service.update_department(department_id, payload, updater_id=current_user.id)


# --- Employees ---
@router.get("/employees", response_model=PaginatedEmployeesResponse)
def list_employees(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    department_id: int | None = Query(None),
    is_active: bool | None = Query(None),
) -> PaginatedEmployeesResponse:
    employees, total = service.list_employees(
        page=page, page_size=page_size, department_id=department_id, is_active=is_active
    )
    return PaginatedEmployeesResponse(
        items=[EmployeeResponse.model_validate(e) for e in employees],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
) -> Employee:
    return service.get_employee(employee_id)


@router.post("/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate,
    current_user: Annotated[User, Depends(require_superuser)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
) -> Employee:
    return service.create_employee(payload, creator_id=current_user.id)


@router.patch("/employees/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    current_user: Annotated[User, Depends(require_superuser)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
) -> Employee:
    return service.update_employee(employee_id, payload, updater_id=current_user.id)


@router.post("/employees/{employee_id}/deactivate", response_model=EmployeeResponse)
def deactivate_employee(
    employee_id: int,
    current_user: Annotated[User, Depends(require_superuser)],
    service: Annotated[OrganizationService, Depends(get_org_service)],
) -> Employee:
    return service.deactivate_employee(employee_id, updater_id=current_user.id)
