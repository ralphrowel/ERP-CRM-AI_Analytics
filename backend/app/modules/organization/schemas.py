from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Company Settings ---
class CompanySettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    legal_name: str
    trade_name: str | None = None
    tin: str | None = None
    address: str | None = None
    currency_code: str
    timezone: str
    updated_at: datetime


class CompanySettingsUpdate(BaseModel):
    legal_name: str = Field(..., min_length=2)
    trade_name: str | None = None
    tin: str | None = None
    address: str | None = None


# --- Departments ---
class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    name: str = Field(..., min_length=2, max_length=100)


class DepartmentUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


# --- Employees ---
class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_no: str
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    department_id: int
    job_title: str | None = None
    manager_id: int | None = None
    user_id: int | None = None
    hire_date: date
    termination_date: date | None = None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class EmployeeCreate(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: EmailStr | None = None
    phone: str | None = None
    department_id: int
    job_title: str | None = None
    manager_id: int | None = None
    user_id: int | None = None
    hire_date: date
    termination_date: date | None = None


class EmployeeUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    department_id: int | None = None
    job_title: str | None = None
    manager_id: int | None = None
    user_id: int | None = None
    hire_date: date | None = None
    termination_date: date | None = None
    is_active: bool | None = None
    version: int = Field(..., description="Optimistic locking version")


class PaginatedEmployeesResponse(BaseModel):
    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int
