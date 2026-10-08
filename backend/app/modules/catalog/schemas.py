from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductCategoryCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    parent_id: int | None = None


class ProductCategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str | None = None
    category_id: int | None = None
    product_type: Literal["stock", "service"]
    uom: Literal["pc", "box", "pack", "kg", "l", "m", "hr"]
    list_price: Decimal
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    sku: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    category_id: int | None = None
    product_type: Literal["stock", "service"] = "stock"
    uom: Literal["pc", "box", "pack", "kg", "l", "m", "hr"] = "pc"
    list_price: Decimal = Field(Decimal("0.0000"), ge=0)


class ProductUpdate(BaseModel):
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    product_type: Literal["stock", "service"] | None = None
    uom: Literal["pc", "box", "pack", "kg", "l", "m", "hr"] | None = None
    list_price: Decimal | None = Field(None, ge=0)
    is_active: bool | None = None
    version: int = Field(..., description="Optimistic locking version")


class PaginatedProductsResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
