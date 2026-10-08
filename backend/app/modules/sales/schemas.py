from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaxRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    rate: str
    is_default: bool
    is_active: bool

    @field_validator("rate", mode="before")
    @classmethod
    def serialize_rate(cls, v: Decimal | str) -> str:
        return f"{Decimal(str(v)):.4f}"


class LineItemPayload(BaseModel):
    product_id: int | None = None
    description: str | None = None
    uom: str = "pc"
    quantity: Decimal = Field(..., gt=Decimal("0.000"))
    unit_price: Decimal = Field(..., ge=Decimal("0.0000"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    tax_rate_id: int | None = None


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_no: int
    product_id: int | None
    description: str
    uom: str
    quantity: str
    unit_price: str
    discount_amount: str
    tax_rate_id: int
    tax_rate: str
    line_net: str
    line_tax: str
    line_total: str

    @field_validator(
        "quantity",
        "unit_price",
        "discount_amount",
        "tax_rate",
        "line_net",
        "line_tax",
        "line_total",
        mode="before",
    )
    @classmethod
    def serialize_decimals(cls, v: Decimal | str) -> str:
        return str(v)


class SalesOrderItemOut(LineItemOut):
    quantity_invoiced: str
    quantity_shipped: str

    @field_validator("quantity_invoiced", "quantity_shipped", mode="before")
    @classmethod
    def serialize_tracking_decimals(cls, v: Decimal | str) -> str:
        return str(v)


# --- Quotes Schemas ---


class QuoteCreatePayload(BaseModel):
    customer_id: int
    opportunity_id: int | None = None
    contact_id: int | None = None
    issue_date: date | None = None
    valid_until: date | None = None
    notes: str | None = None
    items: list[LineItemPayload] = Field(default_factory=list)


class QuoteUpdatePayload(BaseModel):
    contact_id: int | None = None
    valid_until: date | None = None
    notes: str | None = None
    items: list[LineItemPayload] = Field(default_factory=list)
    version: int


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quote_no: str
    customer_id: int
    opportunity_id: int | None
    contact_id: int | None
    status: str
    issue_date: date | None
    valid_until: date | None
    owner_user_id: int | None
    notes: str | None
    currency_code: str
    subtotal: str
    discount_total: str
    tax_total: str
    grand_total: str
    version: int
    items: list[LineItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("subtotal", "discount_total", "tax_total", "grand_total", mode="before")
    @classmethod
    def serialize_totals(cls, v: Decimal | str) -> str:
        return str(v)


class PaginatedQuotes(BaseModel):
    items: list[QuoteOut]
    total: int
    page: int
    page_size: int


# --- Sales Orders Schemas ---


class SalesOrderCreatePayload(BaseModel):
    customer_id: int
    quote_id: int | None = None
    contact_id: int | None = None
    order_date: date | None = None
    requested_delivery_date: date | None = None
    notes: str | None = None
    items: list[LineItemPayload] = Field(default_factory=list)


class SalesOrderUpdatePayload(BaseModel):
    contact_id: int | None = None
    requested_delivery_date: date | None = None
    notes: str | None = None
    items: list[LineItemPayload] = Field(default_factory=list)
    version: int


class SalesOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    customer_id: int
    quote_id: int | None
    contact_id: int | None
    status: str
    order_date: date
    requested_delivery_date: date | None
    billing_address_snapshot: str
    shipping_address_snapshot: str
    payment_terms_days_snapshot: int
    cancel_reason: str | None
    owner_user_id: int | None
    notes: str | None
    currency_code: str
    subtotal: str
    discount_total: str
    tax_total: str
    grand_total: str
    version: int
    items: list[SalesOrderItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("subtotal", "discount_total", "tax_total", "grand_total", mode="before")
    @classmethod
    def serialize_so_totals(cls, v: Decimal | str) -> str:
        return str(v)


class PaginatedSalesOrders(BaseModel):
    items: list[SalesOrderOut]
    total: int
    page: int
    page_size: int


class TransitionRequest(BaseModel):
    reason: str | None = None
