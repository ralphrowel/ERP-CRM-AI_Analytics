from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ── Supplier Product Schemas ─────────────────────────────────────────
class SupplierProductCreate(BaseModel):
    product_id: int
    supplier_sku: str | None = None
    last_unit_cost: Decimal | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    is_preferred: bool = False


class SupplierProductUpdate(BaseModel):
    supplier_sku: str | None = None
    last_unit_cost: Decimal | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    is_preferred: bool | None = None


class SupplierProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: int
    product_id: int
    product_name: str | None = None
    product_sku: str | None = None
    product_uom: str | None = None
    supplier_sku: str | None = None
    last_unit_cost: Decimal | None = None
    lead_time_days: int | None = None
    is_preferred: bool


# ── Supplier Schemas ──────────────────────────────────────────────────
class SupplierBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    tin: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    payment_terms_days: int = Field(default=30, ge=0)
    is_active: bool = True
    notes: str | None = None


class SupplierCreate(SupplierBase):
    supplier_no: str | None = Field(default=None, max_length=50)


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    tin: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    payment_terms_days: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    notes: str | None = None
    version: int


class SupplierOut(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_no: str
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    updated_by: int | None = None
    products: list[SupplierProductOut] = []


class SupplierListOut(BaseModel):
    items: list[SupplierOut]
    total: int
    page: int
    page_size: int


# ── Purchase Order Item Schemas ───────────────────────────────────────
class PurchaseOrderItemPayload(BaseModel):
    product_id: int
    description: str | None = None
    uom: str | None = None
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0)
    tax_rate_id: int


class PurchaseOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_order_id: int
    line_no: int
    product_id: int
    product_name: str | None = None
    product_sku: str | None = None
    description: str
    uom: str
    quantity: Decimal
    unit_cost: Decimal
    tax_rate_id: int
    tax_rate: Decimal
    line_net: Decimal
    line_tax: Decimal
    line_total: Decimal
    quantity_received: Decimal
    quantity_billed: Decimal


# ── Purchase Order Schemas ────────────────────────────────────────────
class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    warehouse_id: int
    order_date: date | None = None
    expected_date: date | None = None
    notes: str | None = None
    items: list[PurchaseOrderItemPayload] = Field(..., min_length=1)


class PurchaseOrderUpdate(BaseModel):
    warehouse_id: int | None = None
    order_date: date | None = None
    expected_date: date | None = None
    notes: str | None = None
    items: list[PurchaseOrderItemPayload] | None = None
    version: int


class PurchaseOrderClosePayload(BaseModel):
    reason: str = Field(..., min_length=3)


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    po_no: str
    supplier_id: int
    supplier_name: str | None = None
    warehouse_id: int
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    status: str
    order_date: date
    expected_date: date | None = None
    notes: str | None = None
    payment_terms_days_snapshot: int
    supplier_address_snapshot: str | None = None
    warehouse_address_snapshot: str | None = None
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    updated_by: int | None = None
    items: list[PurchaseOrderItemOut] = []


class PurchaseOrderListOut(BaseModel):
    items: list[PurchaseOrderOut]
    total: int
    page: int
    page_size: int


# ── Goods Receipt Schemas ─────────────────────────────────────────────
class GoodsReceiptItemPayload(BaseModel):
    purchase_order_item_id: int
    quantity: Decimal = Field(..., gt=0)


class GoodsReceiptCreate(BaseModel):
    purchase_order_id: int
    supplier_delivery_ref: str | None = None
    notes: str | None = None
    items: list[GoodsReceiptItemPayload] = Field(..., min_length=1)


class GoodsReceiptItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goods_receipt_id: int
    purchase_order_item_id: int
    product_id: int
    product_name: str | None = None
    product_sku: str | None = None
    quantity: Decimal
    unit_cost: Decimal


class GoodsReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gr_no: str
    purchase_order_id: int
    po_no: str | None = None
    warehouse_id: int
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    status: str
    received_at: datetime | None = None
    supplier_delivery_ref: str | None = None
    notes: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    items: list[GoodsReceiptItemOut] = []


class GoodsReceiptListOut(BaseModel):
    items: list[GoodsReceiptOut]
    total: int
    page: int
    page_size: int


# ── Supplier Invoice (Bill) Schemas ───────────────────────────────────
class SupplierInvoiceItemPayload(BaseModel):
    purchase_order_item_id: int
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0)


class SupplierInvoiceCreate(BaseModel):
    purchase_order_id: int
    supplier_invoice_ref: str = Field(..., min_length=1, max_length=100)
    invoice_date: date | None = None
    due_date: date | None = None
    notes: str | None = None
    items: list[SupplierInvoiceItemPayload] = Field(..., min_length=1)


class SupplierInvoiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_invoice_id: int
    purchase_order_item_id: int
    product_id: int
    product_name: str | None = None
    product_sku: str | None = None
    line_no: int
    description: str
    uom: str
    quantity: Decimal
    unit_cost: Decimal
    tax_rate_id: int
    tax_rate: Decimal
    line_net: Decimal
    line_tax: Decimal
    line_total: Decimal


class SupplierInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bill_no: str
    supplier_id: int
    supplier_name: str | None = None
    purchase_order_id: int
    po_no: str | None = None
    supplier_invoice_ref: str
    status: str
    invoice_date: date
    due_date: date
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    match_notes: str | None = None
    notes: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    items: list[SupplierInvoiceItemOut] = []


class SupplierInvoiceListOut(BaseModel):
    items: list[SupplierInvoiceOut]
    total: int
    page: int
    page_size: int


# ── Supplier Payment & Allocation Schemas ─────────────────────────────
class SupplierPaymentAllocationItem(BaseModel):
    supplier_invoice_id: int
    amount: Decimal = Field(..., gt=0)


class SupplierPaymentCreate(BaseModel):
    supplier_id: int
    payment_date: date | None = None
    payment_method: str = Field(default="bank_transfer")
    reference_no: str | None = None
    amount: Decimal = Field(..., gt=0)
    notes: str | None = None
    allocations: list[SupplierPaymentAllocationItem] = []


class SupplierPaymentAllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_payment_id: int
    supplier_invoice_id: int
    bill_no: str | None = None
    supplier_invoice_ref: str | None = None
    amount: Decimal
    allocated_at: datetime


class SupplierPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payment_no: str
    supplier_id: int
    supplier_name: str | None = None
    payment_date: date
    payment_method: str
    reference_no: str | None = None
    amount: Decimal
    amount_allocated: Decimal
    status: str
    void_reason: str | None = None
    voided_at: datetime | None = None
    notes: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    allocations: list[SupplierPaymentAllocationOut] = []


class SupplierPaymentListOut(BaseModel):
    items: list[SupplierPaymentOut]
    total: int
    page: int
    page_size: int


class SupplierPaymentVoidPayload(BaseModel):
    reason: str = Field(..., min_length=3)


# ── Supplier Statement Schemas ────────────────────────────────────────
class SupplierStatementBillItem(BaseModel):
    id: int
    bill_no: str
    supplier_invoice_ref: str
    invoice_date: date
    due_date: date
    grand_total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    status: str


class SupplierStatementPaymentItem(BaseModel):
    id: int
    payment_no: str
    payment_date: date
    payment_method: str
    reference_no: str | None = None
    amount: Decimal
    amount_allocated: Decimal
    status: str


class SupplierStatementOut(BaseModel):
    supplier_id: int
    supplier_no: str
    supplier_name: str
    bills: list[SupplierStatementBillItem]
    payments: list[SupplierStatementPaymentItem]
    total_billed: Decimal
    total_paid: Decimal
    total_outstanding: Decimal
