from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.sales.schemas import (
    PaginatedQuotes,
    PaginatedSalesOrders,
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
    _: Annotated[User, Depends(get_current_user)],
) -> list[TaxRateOut]:
    rates = service.list_tax_rates()
    return [TaxRateOut.model_validate(r) for r in rates]


# --- Quotes ---


@router.get("/quotes", response_model=PaginatedQuotes)
def list_quotes(
    service: Annotated[SalesService, Depends(get_sales_service)],
    _: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedQuotes:
    items, total = service.list_quotes(
        page=page, page_size=page_size, customer_id=customer_id, status=status
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
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuoteOut:
    quote = service.create_quote(payload, current_user_id=current_user.id)
    return QuoteOut.model_validate(quote)


@router.get("/quotes/{quote_id}", response_model=QuoteOut)
def get_quote(
    quote_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    _: Annotated[User, Depends(get_current_user)],
) -> QuoteOut:
    quote = service.get_quote(quote_id)
    return QuoteOut.model_validate(quote)


@router.put("/quotes/{quote_id}", response_model=QuoteOut)
def update_quote(
    quote_id: int,
    payload: QuoteUpdatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuoteOut:
    quote = service.update_quote(quote_id, payload, current_user_id=current_user.id)
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/send", response_model=QuoteOut)
def send_quote(
    quote_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuoteOut:
    quote = service.send_quote(quote_id, current_user_id=current_user.id)
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/accept", response_model=QuoteOut)
def accept_quote(
    quote_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuoteOut:
    quote = service.accept_quote(quote_id, current_user_id=current_user.id)
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/reject", response_model=QuoteOut)
def reject_quote(
    quote_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuoteOut:
    quote = service.reject_quote(quote_id, reason=payload.reason, current_user_id=current_user.id)
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/cancel", response_model=QuoteOut)
def cancel_quote(
    quote_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuoteOut:
    quote = service.cancel_quote(quote_id, reason=payload.reason, current_user_id=current_user.id)
    return QuoteOut.model_validate(quote)


@router.post("/quotes/{quote_id}/create-order", response_model=SalesOrderOut)
def create_order_from_quote(
    quote_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SalesOrderOut:
    order = service.create_order_from_quote(quote_id, current_user_id=current_user.id)
    return SalesOrderOut.model_validate(order)


# --- Sales Orders ---


@router.get("/sales-orders", response_model=PaginatedSalesOrders)
def list_sales_orders(
    service: Annotated[SalesService, Depends(get_sales_service)],
    _: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedSalesOrders:
    items, total = service.list_sales_orders(
        page=page, page_size=page_size, customer_id=customer_id, status=status
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
    current_user: Annotated[User, Depends(get_current_user)],
) -> SalesOrderOut:
    order = service.create_sales_order(payload, current_user_id=current_user.id)
    return SalesOrderOut.model_validate(order)


@router.get("/sales-orders/{order_id}", response_model=SalesOrderOut)
def get_sales_order(
    order_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    _: Annotated[User, Depends(get_current_user)],
) -> SalesOrderOut:
    order = service.get_sales_order(order_id)
    return SalesOrderOut.model_validate(order)


@router.put("/sales-orders/{order_id}", response_model=SalesOrderOut)
def update_sales_order(
    order_id: int,
    payload: SalesOrderUpdatePayload,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SalesOrderOut:
    order = service.update_sales_order(order_id, payload, current_user_id=current_user.id)
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/confirm", response_model=SalesOrderOut)
def confirm_sales_order(
    order_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SalesOrderOut:
    order = service.confirm_sales_order(order_id, current_user_id=current_user.id)
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/hold", response_model=SalesOrderOut)
def hold_sales_order(
    order_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SalesOrderOut:
    order = service.hold_sales_order(
        order_id, reason=payload.reason, current_user_id=current_user.id
    )
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/release", response_model=SalesOrderOut)
def release_sales_order(
    order_id: int,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SalesOrderOut:
    order = service.release_sales_order(order_id, current_user_id=current_user.id)
    return SalesOrderOut.model_validate(order)


@router.post("/sales-orders/{order_id}/cancel", response_model=SalesOrderOut)
def cancel_sales_order(
    order_id: int,
    payload: TransitionRequest,
    service: Annotated[SalesService, Depends(get_sales_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SalesOrderOut:
    order = service.cancel_sales_order(
        order_id, reason=payload.reason, current_user_id=current_user.id
    )
    return SalesOrderOut.model_validate(order)
