from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerAddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    address_type: Literal["billing", "shipping"]
    line1: str
    line2: str | None = None
    barangay: str | None = None
    city: str
    province: str | None = None
    postal_code: str | None = None
    country_code: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerAddressCreate(BaseModel):
    address_type: Literal["billing", "shipping"]
    line1: str = Field(..., min_length=2)
    line2: str | None = None
    barangay: str | None = None
    city: str = Field(..., min_length=2)
    province: str | None = None
    postal_code: str | None = None
    country_code: str = Field("PH", min_length=2, max_length=2)
    is_default: bool = False


class CustomerAddressUpdate(BaseModel):
    address_type: Literal["billing", "shipping"] | None = None
    line1: str | None = None
    line2: str | None = None
    barangay: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_no: str
    name: str
    customer_type: Literal["company", "individual"]
    status: Literal["prospect", "active", "inactive"]
    tin: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    industry: str | None = None
    payment_terms_days: int
    credit_limit: Decimal | None = None
    owner_user_id: int | None = None
    notes: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    addresses: list[CustomerAddressResponse] = []


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=2)
    customer_type: Literal["company", "individual"] = "company"
    status: Literal["prospect", "active", "inactive"] = "active"
    tin: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    industry: str | None = None
    payment_terms_days: int = Field(0, ge=0)
    credit_limit: Decimal | None = Field(None, ge=0)
    owner_user_id: int | None = None
    notes: str | None = None
    initial_address: CustomerAddressCreate | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    customer_type: Literal["company", "individual"] | None = None
    status: Literal["prospect", "active", "inactive"] | None = None
    tin: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    industry: str | None = None
    payment_terms_days: int | None = Field(None, ge=0)
    credit_limit: Decimal | None = Field(None, ge=0)
    owner_user_id: int | None = None
    notes: str | None = None
    version: int = Field(..., description="Optimistic locking version")


class PaginatedCustomersResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int
