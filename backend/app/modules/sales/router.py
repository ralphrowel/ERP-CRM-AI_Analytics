import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, require
from app.core.database import get_db
from app.modules.sales.schemas import (
    CreditNoteCreatePayload,
    CreditNoteOut,
    CustomerStatementOut,
    InvoiceCreateFromOrderPayload,
    InvoiceIssuePayload,
    InvoiceOut,
    PaginatedCreditNotes,
    PaginatedInvoices,
    PaginatedPayments,
    PaginatedQuotes,
    PaginatedSalesOrders,
    PaymentAllocationCreatePayload,
    PaymentAllocationOut,
    PaymentCreatePayload,
    PaymentOut,
    QuoteCreatePayload,
    QuoteOut,
    QuoteUpdatePayload,
    SalesOrderCreatePayload,
    SalesOrderOut,
    SalesOrderUpdatePayload,
    TaxRateOut,
    TransitionRequest,
)
from app.modules.sales.service import SalesService

router = APIRouter(prefix="", tags=["Sales & Transactions"])


def get_sales_service(db: Annotated[Session, Depends(get_db)]) -> SalesService:
    return SalesService(db)


# --- Tax Rates ---


@router.get("/tax-rates", response_model=list[TaxRateOut])
def list_tax_rates(
    service: Annotated[SalesService, Depends(get_sales_service)],
    _: Annotated[ScopeContext, Depends(require("tax_rate:read"))],
) -> list[TaxRateOut]:
    rates = service.list_tax_rates()
    return [TaxRateOut.model_validate(r) for r in rates]


# --- Quotes ---


@router.get("/quotes", response_model=PaginatedQuotes)
def list_quotes(
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("quote:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedQuotes:
    items, total = service.list_quotes(
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        status=status,
        scope_context=ctx,
    )
    return PaginatedQuotes(
        items=[QuoteOut.model_validate(q) for q in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/quotes", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
def create_quote(
    payload: QuoteCreatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("quote:create"))],
) -> QuoteOut:
    quote = service.create_quote(payload, current_user_id=ctx.user.id)
    return QuoteOut.model_validate(quote)


@router.get("/quotes/{quote_id}", response_model=QuoteOut)
def get_quote(
    quote_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("quote:read"))],
) -> QuoteOut:
    quote = service.get_quote(quote_id, scope_context=ctx)
    return QuoteOut.model_validate(quote)


@router.put("/quotes/{quote_id}", response_model=QuoteOut)
def update_quote(
    quote_id: int,
    payload: QuoteUpdatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("quote:update"))],
) -> QuoteOut:
    quote = service.update_quote(quote_id, payload, current_user_id=ctx.user.id, scope_context=ctx)
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/send", response_model=QuoteOut)
def send_quote(
    quote_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("quote:send"))],
) -> QuoteOut:
    quote = service.send_quote(quote_id, current_user_id=ctx.user.id, scope_context=ctx)
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/accept", response_model=QuoteOut)
def accept_quote(
    quote_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("quote:accept"))],
) -> QuoteOut:
    quote = service.accept_quote(quote_id, current_user_id=ctx.user.id, scope_context=ctx)
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/reject", response_model=QuoteOut)
def reject_quote(
    quote_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("quote:reject"))],
) -> QuoteOut:
    quote = service.reject_quote(
        quote_id, reason=payload.reason, current_user_id=ctx.user.id, scope_context=ctx
    )
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/cancel", response_model=QuoteOut)
def cancel_quote(
    quote_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("quote:update"))],
) -> QuoteOut:
    quote = service.cancel_quote(
        quote_id, reason=payload.reason, current_user_id=ctx.user.id, scope_context=ctx
    )
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/create-order", response_model=SalesOrderOut)
def create_order_from_quote(
    quote_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:create"))],
) -> SalesOrderOut:
    order = service.create_order_from_quote(
        quote_id, current_user_id=ctx.user.id, scope_context=ctx
    )
    return SalesOrderOut.model_validate(order)


# --- Sales Orders ---


@router.get("/sales-orders", response_model=PaginatedSalesOrders)
def list_sales_orders(
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedSalesOrders:
    items, total = service.list_sales_orders(
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        status=status,
        scope_context=ctx,
    )
    return PaginatedSalesOrders(
        items=[SalesOrderOut.model_validate(so) for so in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/sales-orders", response_model=SalesOrderOut, status_code=status.HTTP_201_CREATED)
def create_sales_order(
    payload: SalesOrderCreatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:create"))],
) -> SalesOrderOut:
    order = service.create_sales_order(payload, current_user_id=ctx.user.id)
    return SalesOrderOut.model_validate(order)


@router.get("/sales-orders/{order_id}", response_model=SalesOrderOut)
def get_sales_order(
    order_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:read"))],
) -> SalesOrderOut:
    order = service.get_sales_order(order_id, scope_context=ctx)
    return SalesOrderOut.model_validate(order)


@router.put("/sales-orders/{order_id}", response_model=SalesOrderOut)
def update_sales_order(
    order_id: int,
    payload: SalesOrderUpdatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:update"))],
) -> SalesOrderOut:
    order = service.update_sales_order(
        order_id, payload, current_user_id=ctx.user.id, scope_context=ctx
    )
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/confirm", response_model=SalesOrderOut)
def confirm_sales_order(
    order_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:confirm"))],
) -> SalesOrderOut:
    order = service.confirm_sales_order(order_id, current_user_id=ctx.user.id, scope_context=ctx)
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/hold", response_model=SalesOrderOut)
def hold_sales_order(
    order_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:update"))],
) -> SalesOrderOut:
    order = service.hold_sales_order(
        order_id, reason=payload.reason, current_user_id=ctx.user.id, scope_context=ctx
    )
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/release", response_model=SalesOrderOut)
def release_sales_order(
    order_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:update"))],
) -> SalesOrderOut:
    order = service.release_sales_order(order_id, current_user_id=ctx.user.id, scope_context=ctx)
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/cancel", response_model=SalesOrderOut)
def cancel_sales_order(
    order_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("sales_order:cancel"))],
) -> SalesOrderOut:
    order = service.cancel_sales_order(
        order_id, reason=payload.reason, current_user_id=ctx.user.id, scope_context=ctx
    )
    return SalesOrderOut.model_validate(order)


@router.post(
    "/sales-orders/{order_id}/create-invoice",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_invoice_from_order(
    order_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("invoice:create"))],
    payload: InvoiceCreateFromOrderPayload | None = None,
) -> InvoiceOut:
    invoice = service.create_invoice_from_order(
        order_id=order_id, payload=payload, current_user_id=ctx.user.id, scope_context=ctx
    )
    return InvoiceOut.model_validate(invoice)


# --- Invoices ---


@router.get("/invoices", response_model=PaginatedInvoices)
def list_invoices(
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("invoice:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
    sales_order_id: int | None = Query(None),
) -> PaginatedInvoices:
    items, total = service.list_invoices(
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        status=status,
        sales_order_id=sales_order_id,
        scope_context=ctx,
    )
    return PaginatedInvoices(
        items=[InvoiceOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("invoice:read"))],
) -> InvoiceOut:
    inv = service.get_invoice(invoice_id, scope_context=ctx)
    return InvoiceOut.model_validate(inv)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceOut)
def issue_invoice(
    invoice_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("invoice:issue"))],
    payload: InvoiceIssuePayload | None = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Any:
    request_hash = ""
    if idempotency_key:
        raw_body = payload.model_dump_json() if payload else "{}"
        request_hash = hashlib.sha256(f"issue:{invoice_id}:{raw_body}".encode()).hexdigest()
        is_cached, cached_status, cached_body = service.check_idempotency(
            user_id=ctx.user.id, key=idempotency_key, request_hash=request_hash
        )
        if is_cached:
            return Response(
                content=json.dumps(cached_body),
                status_code=cached_status or status.HTTP_200_OK,
                media_type="application/json",
            )

    issue_date = payload.issue_date if payload else None
    due_date = payload.due_date if payload else None
    inv = service.issue_invoice(
        invoice_id=invoice_id,
        issue_date=issue_date,
        due_date=due_date,
        current_user_id=ctx.user.id,
        scope_context=ctx,
    )
    result = InvoiceOut.model_validate(inv)

    if idempotency_key:
        service.record_idempotency_result(
            user_id=ctx.user.id,
            key=idempotency_key,
            method="POST",
            path=f"/invoices/{invoice_id}/issue",
            request_hash=request_hash,
            status_code=status.HTTP_200_OK,
            response_body=result.model_dump(mode="json"),
        )

    return result


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceOut)
def void_invoice(
    invoice_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("invoice:void"))],
) -> InvoiceOut:
    inv = service.void_invoice(
        invoice_id=invoice_id,
        reason=payload.reason,
        current_user_id=ctx.user.id,
        scope_context=ctx,
    )
    return InvoiceOut.model_validate(inv)


# --- Payments ---


@router.get("/payments", response_model=PaginatedPayments)
def list_payments(
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("payment:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedPayments:
    items, total = service.list_payments(
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        status=status,
        scope_context=ctx,
    )
    pay_outs = []
    for p in items:
        p_out = PaymentOut.model_validate(p)
        p_out.unallocated_amount = str(p.amount - p.amount_allocated)
        pay_outs.append(p_out)

    return PaginatedPayments(
        items=pay_outs,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("payment:create"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Any:
    request_hash = ""
    if idempotency_key:
        raw_body = payload.model_dump_json()
        request_hash = hashlib.sha256(raw_body.encode()).hexdigest()
        is_cached, cached_status, cached_body = service.check_idempotency(
            user_id=ctx.user.id, key=idempotency_key, request_hash=request_hash
        )
        if is_cached:
            return Response(
                content=json.dumps(cached_body),
                status_code=cached_status or status.HTTP_201_CREATED,
                media_type="application/json",
            )

    payment = service.create_payment(payload, current_user_id=ctx.user.id)
    result = PaymentOut.model_validate(payment)
    result.unallocated_amount = str(payment.amount - payment.amount_allocated)

    if idempotency_key:
        service.record_idempotency_result(
            user_id=ctx.user.id,
            key=idempotency_key,
            method="POST",
            path="/payments",
            request_hash=request_hash,
            status_code=status.HTTP_201_CREATED,
            response_body=result.model_dump(mode="json"),
        )

    return result


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("payment:read"))],
) -> PaymentOut:
    p = service.get_payment(payment_id, scope_context=ctx)
    p_out = PaymentOut.model_validate(p)
    p_out.unallocated_amount = str(p.amount - p.amount_allocated)
    return p_out


@router.post(
    "/payments/{payment_id}/allocations",
    response_model=PaymentAllocationOut,
    status_code=status.HTTP_201_CREATED,
)
def allocate_payment(
    payment_id: int,
    payload: PaymentAllocationCreatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("payment:create"))],
) -> PaymentAllocationOut:
    alloc = service.allocate_payment(
        payment_id=payment_id,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        current_user_id=ctx.user.id,
        scope_context=ctx,
    )
    return PaymentAllocationOut.model_validate(alloc)


@router.post("/payments/{payment_id}/void", response_model=PaymentOut)
def void_payment(
    payment_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("payment:void"))],
) -> PaymentOut:
    pay = service.void_payment(
        payment_id=payment_id,
        reason=payload.reason,
        current_user_id=ctx.user.id,
        scope_context=ctx,
    )
    p_out = PaymentOut.model_validate(pay)
    p_out.unallocated_amount = str(pay.amount - pay.amount_allocated)
    return p_out


# --- Credit Notes ---


@router.get("/credit-notes", response_model=PaginatedCreditNotes)
def list_credit_notes(
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("credit_note:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None),
    invoice_id: int | None = Query(None),
) -> PaginatedCreditNotes:
    items, total = service.list_credit_notes(
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        invoice_id=invoice_id,
        scope_context=ctx,
    )
    return PaginatedCreditNotes(
        items=[CreditNoteOut.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/credit-notes", response_model=CreditNoteOut, status_code=status.HTTP_201_CREATED)
def create_credit_note(
    payload: CreditNoteCreatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("credit_note:create"))],
) -> CreditNoteOut:
    cn = service.create_credit_note(payload, current_user_id=ctx.user.id)
    return CreditNoteOut.model_validate(cn)


@router.get("/credit-notes/{credit_note_id}", response_model=CreditNoteOut)
def get_credit_note(
    credit_note_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("credit_note:read"))],
) -> CreditNoteOut:
    cn = service.get_credit_note(credit_note_id, scope_context=ctx)
    return CreditNoteOut.model_validate(cn)


# --- Customer Statement ---


@router.get("/customers/{customer_id}/statement", response_model=CustomerStatementOut)
def get_customer_statement(
    customer_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    ctx: Annotated[ScopeContext, Depends(require("customer_statement:read"))],
) -> CustomerStatementOut:
    return service.get_customer_statement(customer_id, scope_context=ctx)
