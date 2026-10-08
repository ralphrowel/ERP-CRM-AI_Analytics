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
    warehouse_id: int | None = None
    quote_id: int | None = None
    contact_id: int | None = None
    order_date: date | None = None
    requested_delivery_date: date | None = None
    notes: str | None = None
    items: list[LineItemPayload] = Field(default_factory=list)


class SalesOrderUpdatePayload(BaseModel):
    warehouse_id: int | None = None
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
    warehouse_id: int
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


# --- Invoices Schemas ---


class InvoiceItemOut(LineItemOut):
    sales_order_item_id: int | None = None


class InvoiceItemCreatePayload(BaseModel):
    sales_order_item_id: int | None = None
    product_id: int | None = None
    description: str | None = None
    uom: str = "pc"
    quantity: Decimal = Field(..., gt=Decimal("0.000"))
    unit_price: Decimal = Field(..., ge=Decimal("0.0000"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    tax_rate_id: int | None = None


class InvoiceCreateFromOrderPayload(BaseModel):
    items: list[InvoiceItemCreatePayload] | None = None


class InvoiceIssuePayload(BaseModel):
    issue_date: date | None = None
    due_date: date | None = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_no: str | None
    customer_id: int
    sales_order_id: int | None
    status: str
    issue_date: date | None
    due_date: date | None
    customer_name_snapshot: str | None
    customer_tin_snapshot: str | None
    billing_address_snapshot: str | None
    currency_code: str
    subtotal: str
    discount_total: str
    tax_total: str
    grand_total: str
    amount_paid: str
    amount_credited: str
    balance_due: str
    voided_at: datetime | None
    void_reason: str | None
    version: int
    items: list[InvoiceItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "subtotal",
        "discount_total",
        "tax_total",
        "grand_total",
        "amount_paid",
        "amount_credited",
        "balance_due",
        mode="before",
    )
    @classmethod
    def serialize_invoice_totals(cls, v: Decimal | str) -> str:
        return str(v)


class PaginatedInvoices(BaseModel):
    items: list[InvoiceOut]
    total: int
    page: int
    page_size: int


# --- Payments Schemas ---


class PaymentAllocationCreatePayload(BaseModel):
    invoice_id: int
    amount: Decimal = Field(..., gt=Decimal("0.00"))


class PaymentAllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payment_id: int
    invoice_id: int
    amount: str
    allocated_at: datetime
    allocated_by: int | None
    invoice_no: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def serialize_alloc_amount(cls, v: Decimal | str) -> str:
        return str(v)


class PaymentCreatePayload(BaseModel):
    customer_id: int
    payment_date: date | None = None
    method: str
    reference_no: str | None = None
    amount: Decimal = Field(..., gt=Decimal("0.00"))
    allocations: list[PaymentAllocationCreatePayload] = Field(default_factory=list)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payment_no: str
    customer_id: int
    payment_date: date
    method: str
    reference_no: str | None
    amount: str
    amount_allocated: str
    unallocated_amount: str = "0.00"
    status: str
    void_reason: str | None
    version: int
    allocations: list[PaymentAllocationOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("amount", "amount_allocated", "unallocated_amount", mode="before")
    @classmethod
    def serialize_payment_amounts(cls, v: Decimal | str) -> str:
        return str(v)


class PaginatedPayments(BaseModel):
    items: list[PaymentOut]
    total: int
    page: int
    page_size: int


# --- Credit Notes Schemas ---


class CreditNoteItemOut(LineItemOut):
    invoice_item_id: int | None = None


class CreditNoteItemCreatePayload(BaseModel):
    invoice_item_id: int | None = None
    product_id: int | None = None
    description: str | None = None
    uom: str = "pc"
    quantity: Decimal = Field(..., gt=Decimal("0.000"))
    unit_price: Decimal = Field(..., ge=Decimal("0.0000"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    tax_rate_id: int | None = None


class CreditNoteCreatePayload(BaseModel):
    invoice_id: int
    reason: str
    items: list[CreditNoteItemCreatePayload] | None = None


class CreditNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    credit_note_no: str | None
    invoice_id: int
    customer_id: int
    status: str
    issue_date: date | None
    reason: str
    currency_code: str
    subtotal: str
    discount_total: str
    tax_total: str
    grand_total: str
    version: int
    items: list[CreditNoteItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("subtotal", "discount_total", "tax_total", "grand_total", mode="before")
    @classmethod
    def serialize_cn_totals(cls, v: Decimal | str) -> str:
        return str(v)


class PaginatedCreditNotes(BaseModel):
    items: list[CreditNoteOut]
    total: int
    page: int
    page_size: int


# --- Customer AR Statement ---


class StatementTransactionOut(BaseModel):
    date: date
    doc_type: str
    doc_no: str
    reference: str | None = None
    amount_invoiced: str = "0.00"
    amount_paid: str = "0.00"
    running_balance: str = "0.00"


class CustomerStatementOut(BaseModel):
    customer_id: int
    customer_name: str
    statement_date: date
    total_invoiced: str
    total_paid: str
    total_credited: str
    unallocated_credit: str
    open_ar_balance: str
    transactions: list[StatementTransactionOut] = Field(default_factory=list)
