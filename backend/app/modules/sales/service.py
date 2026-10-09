import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.authorization import ScopeContext, apply_scope
from app.core.clock import Clock, get_clock
from app.core.errors import AppException, BusinessRuleError, ConflictError, NotFoundError
from app.core.money import calculate_line, round_money
from app.core.numbering import generate_next_number
from app.core.status_history import record_status_change
from app.modules.catalog.models import Product
from app.modules.crm.models import Customer, CustomerAddress, Opportunity
from app.modules.sales.models import (
    CreditNote,
    CreditNoteItem,
    IdempotencyKey,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAllocation,
    Quote,
    QuoteItem,
    SalesOrder,
    SalesOrderItem,
    TaxRate,
)
from app.modules.sales.schemas import (
    CreditNoteCreatePayload,
    CustomerStatementOut,
    InvoiceCreateFromOrderPayload,
    LineItemPayload,
    PaymentCreatePayload,
    QuoteCreatePayload,
    QuoteUpdatePayload,
    SalesOrderCreatePayload,
    SalesOrderUpdatePayload,
    StatementTransactionOut,
)


class SalesService:
    def __init__(self, db: Session, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or get_clock()

    # --- Tax Rates ---

    def list_tax_rates(self) -> list[TaxRate]:
        stmt = select(TaxRate).where(TaxRate.is_active == True).order_by(TaxRate.id)  # noqa: E712
        return list(self.db.execute(stmt).scalars().all())

    def get_default_tax_rate(self) -> TaxRate:
        stmt = select(TaxRate).where(TaxRate.is_default == True, TaxRate.is_active == True)  # noqa: E712
        tax_rate = self.db.execute(stmt).scalar_one_or_none()
        if not tax_rate:
            # Fallback to any active or create in-memory
            stmt_any = select(TaxRate).where(TaxRate.is_active == True).order_by(TaxRate.id)  # noqa: E712
            tax_rate = self.db.execute(stmt_any).scalars().first()
        if not tax_rate:
            raise NotFoundError("No active default tax rate configured in database.")
        return tax_rate

    # --- Line Calculations Helper ---

    def _prepare_quote_items(
        self, items_payload: list[LineItemPayload], default_tax_rate: TaxRate
    ) -> tuple[list[QuoteItem], Decimal, Decimal, Decimal, Decimal]:
        """Calculates line items and totals strictly per Roadmap §4.3."""
        quote_items: list[QuoteItem] = []
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        tax_total = Decimal("0.00")

        # Cache products and tax rates needed
        product_ids = [p.product_id for p in items_payload if p.product_id is not None]
        products_map: dict[int, Product] = {}
        if product_ids:
            p_stmt = select(Product).where(Product.id.in_(product_ids))
            for prod in self.db.execute(p_stmt).scalars().all():
                products_map[prod.id] = prod

        tax_rate_ids = [p.tax_rate_id for p in items_payload if p.tax_rate_id is not None]
        tax_rates_map: dict[int, TaxRate] = {}
        if tax_rate_ids:
            tr_stmt = select(TaxRate).where(TaxRate.id.in_(tax_rate_ids))
            for tr in self.db.execute(tr_stmt).scalars().all():
                tax_rates_map[tr.id] = tr

        for idx, item_data in enumerate(items_payload, start=1):
            product = products_map.get(item_data.product_id) if item_data.product_id else None

            # Snapshot description & uom
            desc = item_data.description or (product.name if product else f"Line item {idx}")
            uom = item_data.uom or (product.uom if product else "pc")

            # Determine tax rate
            if item_data.tax_rate_id and item_data.tax_rate_id in tax_rates_map:
                tr = tax_rates_map[item_data.tax_rate_id]
            elif product and product.tax_rate_id:
                tr_stmt = select(TaxRate).where(TaxRate.id == product.tax_rate_id)
                tr = self.db.execute(tr_stmt).scalar_one_or_none() or default_tax_rate
            else:
                tr = default_tax_rate

            # Compute line
            calc = calculate_line(
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                discount_amount=item_data.discount_amount,
                tax_rate=tr.rate,
            )

            q_item = QuoteItem(
                line_no=idx,
                product_id=product.id if product else None,
                description=desc,
                uom=uom,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                discount_amount=calc["discount_amount"],
                tax_rate_id=tr.id,
                tax_rate=tr.rate,
                line_net=calc["line_net"],
                line_tax=calc["line_tax"],
                line_total=calc["line_total"],
            )
            quote_items.append(q_item)

            subtotal += calc["line_net"]
            discount_total += calc["discount_amount"]
            tax_total += calc["line_tax"]

        subtotal = round_money(subtotal)
        discount_total = round_money(discount_total)
        tax_total = round_money(tax_total)
        grand_total = round_money(subtotal + tax_total)

        return quote_items, subtotal, discount_total, tax_total, grand_total

    def _prepare_so_items(
        self, items_payload: list[LineItemPayload], default_tax_rate: TaxRate
    ) -> tuple[list[SalesOrderItem], Decimal, Decimal, Decimal, Decimal]:
        """Calculates sales order line items and totals strictly per Roadmap §4.3."""
        so_items: list[SalesOrderItem] = []
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        tax_total = Decimal("0.00")

        product_ids = [p.product_id for p in items_payload if p.product_id is not None]
        products_map: dict[int, Product] = {}
        if product_ids:
            p_stmt = select(Product).where(Product.id.in_(product_ids))
            for prod in self.db.execute(p_stmt).scalars().all():
                products_map[prod.id] = prod

        tax_rate_ids = [p.tax_rate_id for p in items_payload if p.tax_rate_id is not None]
        tax_rates_map: dict[int, TaxRate] = {}
        if tax_rate_ids:
            tr_stmt = select(TaxRate).where(TaxRate.id.in_(tax_rate_ids))
            for tr in self.db.execute(tr_stmt).scalars().all():
                tax_rates_map[tr.id] = tr

        for idx, item_data in enumerate(items_payload, start=1):
            product = products_map.get(item_data.product_id) if item_data.product_id else None

            desc = item_data.description or (product.name if product else f"Line item {idx}")
            uom = item_data.uom or (product.uom if product else "pc")

            if item_data.tax_rate_id and item_data.tax_rate_id in tax_rates_map:
                tr = tax_rates_map[item_data.tax_rate_id]
            elif product and product.tax_rate_id:
                tr_stmt = select(TaxRate).where(TaxRate.id == product.tax_rate_id)
                tr = self.db.execute(tr_stmt).scalar_one_or_none() or default_tax_rate
            else:
                tr = default_tax_rate

            calc = calculate_line(
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                discount_amount=item_data.discount_amount,
                tax_rate=tr.rate,
            )

            so_item = SalesOrderItem(
                line_no=idx,
                product_id=product.id if product else None,
                description=desc,
                uom=uom,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                discount_amount=calc["discount_amount"],
                tax_rate_id=tr.id,
                tax_rate=tr.rate,
                line_net=calc["line_net"],
                line_tax=calc["line_tax"],
                line_total=calc["line_total"],
                quantity_invoiced=Decimal("0.000"),
                quantity_shipped=Decimal("0.000"),
            )
            so_items.append(so_item)

            subtotal += calc["line_net"]
            discount_total += calc["discount_amount"]
            tax_total += calc["line_tax"]

        subtotal = round_money(subtotal)
        discount_total = round_money(discount_total)
        tax_total = round_money(tax_total)
        grand_total = round_money(subtotal + tax_total)

        return so_items, subtotal, discount_total, tax_total, grand_total

    # --- Quotes API ---

    def create_quote(
        self, payload: QuoteCreatePayload, current_user_id: int | None = None
    ) -> Quote:
        customer = self.db.get(Customer, payload.customer_id)
        if not customer:
            raise NotFoundError(f"Customer #{payload.customer_id} not found.")

        default_tr = self.get_default_tax_rate()
        quote_items, subtotal, discount_total, tax_total, grand_total = self._prepare_quote_items(
            payload.items, default_tr
        )

        quote_no = generate_next_number(self.db, "quote", self.clock)

        quote = Quote(
            quote_no=quote_no,
            customer_id=payload.customer_id,
            opportunity_id=payload.opportunity_id,
            contact_id=payload.contact_id,
            status="draft",
            issue_date=payload.issue_date,
            valid_until=payload.valid_until,
            owner_user_id=current_user_id,
            notes=payload.notes,
            currency_code="PHP",
            subtotal=subtotal,
            discount_total=discount_total,
            tax_total=tax_total,
            grand_total=grand_total,
            created_by=current_user_id,
            updated_by=current_user_id,
        )
        quote.items = quote_items
        self.db.add(quote)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="quote",
            entity_id=quote.id,
            from_status=None,
            to_status="draft",
            reason="Quote created as draft",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(quote)
        return quote

    def get_quote(self, quote_id: int, scope_context: ScopeContext | None = None) -> Quote:
        stmt = select(Quote).options(joinedload(Quote.items)).where(Quote.id == quote_id)
        if scope_context:
            stmt = apply_scope(stmt, Quote, scope_context, self.db)
        quote = self.db.execute(stmt).unique().scalar_one_or_none()
        if not quote:
            raise NotFoundError(f"Quote #{quote_id} not found.")
        return quote

    def list_quotes(
        self,
        page: int = 1,
        page_size: int = 20,
        customer_id: int | None = None,
        status: str | None = None,
        scope_context: ScopeContext | None = None,
    ) -> tuple[list[Quote], int]:
        stmt = select(Quote).options(joinedload(Quote.items))
        count_stmt = select(func.count(Quote.id))

        if customer_id:
            stmt = stmt.where(Quote.customer_id == customer_id)
            count_stmt = count_stmt.where(Quote.customer_id == customer_id)
        if status:
            stmt = stmt.where(Quote.status == status)
            count_stmt = count_stmt.where(Quote.status == status)

        if scope_context:
            stmt = apply_scope(stmt, Quote, scope_context, self.db)
            count_stmt = apply_scope(count_stmt, Quote, scope_context, self.db)

        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(Quote.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).unique().scalars().all())
        return items, total

    def update_quote(
        self,
        quote_id: int,
        payload: QuoteUpdatePayload,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Quote:
        quote = self.get_quote(quote_id, scope_context=scope_context)
        if quote.status != "draft":
            raise BusinessRuleError(
                "QUOTE_IMMUTABLE",
                f"Cannot edit quote in status '{quote.status}'. Only drafts are editable.",
            )
        if quote.version != payload.version:
            raise ConflictError("Quote was modified by another transaction. Please reload.")

        default_tr = self.get_default_tax_rate()
        quote_items, subtotal, discount_total, tax_total, grand_total = self._prepare_quote_items(
            payload.items, default_tr
        )

        quote.contact_id = payload.contact_id
        quote.valid_until = payload.valid_until
        quote.notes = payload.notes
        quote.subtotal = subtotal
        quote.discount_total = discount_total
        quote.tax_total = tax_total
        quote.grand_total = grand_total
        quote.version += 1
        quote.updated_by = current_user_id

        # Replace items
        quote.items.clear()
        quote.items.extend(quote_items)

        self.db.commit()
        self.db.refresh(quote)
        return quote

    def send_quote(
        self,
        quote_id: int,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Quote:
        quote = self.get_quote(quote_id, scope_context=scope_context)
        if quote.status != "draft":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only draft quotes can be sent. Current status: '{quote.status}'",
            )

        from_status = quote.status
        quote.status = "sent"
        if not quote.issue_date:
            quote.issue_date = self.clock.today()
        quote.version += 1
        quote.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="quote",
            entity_id=quote.id,
            from_status=from_status,
            to_status="sent",
            reason="Quote sent to customer",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(quote)
        return quote

    def accept_quote(
        self,
        quote_id: int,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Quote:
        quote = self.get_quote(quote_id, scope_context=scope_context)
        if quote.status != "sent":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only sent quotes can be accepted. Current status: '{quote.status}'",
            )

        # Check expiration
        today = self.clock.today()
        if quote.valid_until and quote.valid_until < today:
            raise BusinessRuleError(
                "QUOTE_EXPIRED", f"Quote expired on {quote.valid_until}. Current date: {today}."
            )

        from_status = quote.status
        quote.status = "accepted"
        quote.version += 1
        quote.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="quote",
            entity_id=quote.id,
            from_status=from_status,
            to_status="accepted",
            reason="Quote accepted by customer",
            changed_by=current_user_id,
            clock=self.clock,
        )

        # Roadmap Rule 4: If quote is linked to an opportunity, transition opportunity to 'won'
        if quote.opportunity_id:
            opp = self.db.get(Opportunity, quote.opportunity_id)
            if opp and opp.stage not in ("won", "lost"):
                opp_from_stage = opp.stage
                opp.stage = "won"
                opp.probability = Decimal("1.0000")
                opp.closed_at = self.clock.now()
                opp.version += 1
                opp.updated_by = current_user_id

                record_status_change(
                    self.db,
                    entity_type="opportunity",
                    entity_id=opp.id,
                    from_status=opp_from_stage,
                    to_status="won",
                    reason=f"Won automatically upon acceptance of Quote {quote.quote_no}",
                    changed_by=current_user_id,
                    clock=self.clock,
                )

                # Auto-promote customer from prospect to active
                customer = self.db.get(Customer, opp.customer_id)
                if customer and customer.status == "prospect":
                    cust_from_status = customer.status
                    customer.status = "active"
                    customer.version += 1
                    customer.updated_by = current_user_id
                    record_status_change(
                        self.db,
                        entity_type="customer",
                        entity_id=customer.id,
                        from_status=cust_from_status,
                        to_status="active",
                        reason=f"Auto-promoted on Quote {quote.quote_no} acceptance",
                        changed_by=current_user_id,
                        clock=self.clock,
                    )

        self.db.commit()
        self.db.refresh(quote)
        return quote

    def reject_quote(
        self,
        quote_id: int,
        reason: str | None = None,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Quote:
        quote = self.get_quote(quote_id, scope_context=scope_context)
        if quote.status != "sent":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only sent quotes can be rejected. Current status: '{quote.status}'",
            )

        from_status = quote.status
        quote.status = "rejected"
        quote.version += 1
        quote.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="quote",
            entity_id=quote.id,
            from_status=from_status,
            to_status="rejected",
            reason=reason or "Quote rejected by customer",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(quote)
        return quote

    def cancel_quote(
        self,
        quote_id: int,
        reason: str | None = None,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Quote:
        quote = self.get_quote(quote_id, scope_context=scope_context)
        if quote.status not in ("draft", "sent"):
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Cannot cancel quote in status '{quote.status}'. Only draft or sent quotes can be cancelled.",
            )

        from_status = quote.status
        quote.status = "cancelled"
        quote.version += 1
        quote.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="quote",
            entity_id=quote.id,
            from_status=from_status,
            to_status="cancelled",
            reason=reason or "Quote cancelled",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(quote)
        return quote

    def create_order_from_quote(
        self,
        quote_id: int,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> SalesOrder:
        """Roadmap Rule 5: Creates Sales Order directly from accepted (or sent) quote, copying lines and preserving snapshots."""
        quote = self.get_quote(quote_id, scope_context=scope_context)
        if quote.status not in ("accepted", "sent"):
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Cannot create order from quote in status '{quote.status}'. Quote must be sent or accepted.",
            )

        if not quote.items:
            raise BusinessRuleError("EMPTY_ORDER", "Quote has no line items.")

        order_no = generate_next_number(self.db, "sales_order", self.clock)
        from app.modules.inventory.service import InventoryService

        inv_service = InventoryService(self.db, self.clock)
        default_wh = inv_service.get_default_warehouse()

        so = SalesOrder(
            order_no=order_no,
            customer_id=quote.customer_id,
            warehouse_id=default_wh.id,
            quote_id=quote.id,
            contact_id=quote.contact_id,
            status="draft",
            order_date=self.clock.today(),
            owner_user_id=current_user_id or quote.owner_user_id,
            notes=quote.notes,
            currency_code=quote.currency_code,
            subtotal=quote.subtotal,
            discount_total=quote.discount_total,
            tax_total=quote.tax_total,
            grand_total=quote.grand_total,
            created_by=current_user_id,
            updated_by=current_user_id,
        )

        so_items: list[SalesOrderItem] = []
        for q_item in quote.items:
            so_item = SalesOrderItem(
                line_no=q_item.line_no,
                product_id=q_item.product_id,
                description=q_item.description,
                uom=q_item.uom,
                quantity=q_item.quantity,
                unit_price=q_item.unit_price,
                discount_amount=q_item.discount_amount,
                tax_rate_id=q_item.tax_rate_id,
                tax_rate=q_item.tax_rate,
                line_net=q_item.line_net,
                line_tax=q_item.line_tax,
                line_total=q_item.line_total,
                quantity_invoiced=Decimal("0.000"),
                quantity_shipped=Decimal("0.000"),
            )
            so_items.append(so_item)

        so.items = so_items
        self.db.add(so)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="sales_order",
            entity_id=so.id,
            from_status=None,
            to_status="draft",
            reason=f"Created from Quote {quote.quote_no}",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(so)
        return so

    # --- Sales Orders API ---

    def create_sales_order(
        self, payload: SalesOrderCreatePayload, current_user_id: int | None = None
    ) -> SalesOrder:
        customer = self.db.get(Customer, payload.customer_id)
        if not customer:
            raise NotFoundError(f"Customer #{payload.customer_id} not found.")

        default_tr = self.get_default_tax_rate()
        so_items, subtotal, discount_total, tax_total, grand_total = self._prepare_so_items(
            payload.items, default_tr
        )

        order_no = generate_next_number(self.db, "sales_order", self.clock)
        from app.modules.inventory.service import InventoryService

        inv_service = InventoryService(self.db, self.clock)
        wh_id = payload.warehouse_id or inv_service.get_default_warehouse().id

        so = SalesOrder(
            order_no=order_no,
            customer_id=payload.customer_id,
            warehouse_id=wh_id,
            quote_id=payload.quote_id,
            contact_id=payload.contact_id,
            status="draft",
            order_date=payload.order_date or self.clock.today(),
            requested_delivery_date=payload.requested_delivery_date,
            owner_user_id=current_user_id,
            notes=payload.notes,
            currency_code="PHP",
            subtotal=subtotal,
            discount_total=discount_total,
            tax_total=tax_total,
            grand_total=grand_total,
            created_by=current_user_id,
            updated_by=current_user_id,
        )
        so.items = so_items
        self.db.add(so)
        self.db.flush()

        record_status_change(
            self.db,
            entity_type="sales_order",
            entity_id=so.id,
            from_status=None,
            to_status="draft",
            reason="Sales order created as draft",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(so)
        return so

    def get_sales_order(
        self, order_id: int, scope_context: ScopeContext | None = None
    ) -> SalesOrder:
        stmt = (
            select(SalesOrder)
            .options(joinedload(SalesOrder.items))
            .where(SalesOrder.id == order_id)
        )
        if scope_context:
            stmt = apply_scope(stmt, SalesOrder, scope_context, self.db)
        so = self.db.execute(stmt).unique().scalar_one_or_none()
        if not so:
            raise NotFoundError(f"Sales order #{order_id} not found.")
        return so

    def list_sales_orders(
        self,
        page: int = 1,
        page_size: int = 20,
        customer_id: int | None = None,
        status: str | None = None,
        scope_context: ScopeContext | None = None,
    ) -> tuple[list[SalesOrder], int]:
        stmt = select(SalesOrder).options(joinedload(SalesOrder.items))
        count_stmt = select(func.count(SalesOrder.id))

        if customer_id:
            stmt = stmt.where(SalesOrder.customer_id == customer_id)
            count_stmt = count_stmt.where(SalesOrder.customer_id == customer_id)
        if status:
            stmt = stmt.where(SalesOrder.status == status)
            count_stmt = count_stmt.where(SalesOrder.status == status)

        if scope_context:
            stmt = apply_scope(stmt, SalesOrder, scope_context, self.db)
            count_stmt = apply_scope(count_stmt, SalesOrder, scope_context, self.db)

        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(SalesOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).unique().scalars().all())
        return items, total

    def update_sales_order(
        self,
        order_id: int,
        payload: SalesOrderUpdatePayload,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> SalesOrder:
        so = self.get_sales_order(order_id, scope_context=scope_context)
        if so.status != "draft":
            raise BusinessRuleError(
                "ORDER_IMMUTABLE",
                f"Cannot edit order in status '{so.status}'. Only drafts are editable.",
            )
        if so.version != payload.version:
            raise ConflictError("Sales order was modified by another transaction. Please reload.")

        default_tr = self.get_default_tax_rate()
        so_items, subtotal, discount_total, tax_total, grand_total = self._prepare_so_items(
            payload.items, default_tr
        )

        if payload.warehouse_id is not None:
            so.warehouse_id = payload.warehouse_id
        so.contact_id = payload.contact_id
        so.requested_delivery_date = payload.requested_delivery_date
        so.notes = payload.notes
        so.subtotal = subtotal
        so.discount_total = discount_total
        so.tax_total = tax_total
        so.grand_total = grand_total
        so.version += 1
        so.updated_by = current_user_id

        so.items.clear()
        so.items.extend(so_items)

        self.db.commit()
        self.db.refresh(so)
        return so

    def _format_address(self, addr: CustomerAddress | None) -> str:
        if not addr:
            return ""
        parts = [addr.line1]
        if addr.line2:
            parts.append(addr.line2)
        if addr.barangay:
            parts.append(addr.barangay)
        parts.append(addr.city)
        if addr.province:
            parts.append(addr.province)
        if addr.postal_code:
            parts.append(addr.postal_code)
        parts.append(addr.country_code)
        return ", ".join(parts)

    def confirm_sales_order(
        self,
        order_id: int,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> SalesOrder:
        """
        Roadmap Rule 6 & 7:
        - Must have >= 1 line.
        - Customer must not be inactive.
        - All products must be active.
        - Address and payment-term snapshots are taken.
        - A prospect customer becomes active.
        - Credit limit check: open AR balance + uninvoiced confirmed orders + this order <= credit_limit.
        """
        so = self.get_sales_order(order_id, scope_context=scope_context)
        if so.status != "draft":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only draft orders can be confirmed. Current status: '{so.status}'",
            )

        if not so.items:
            raise BusinessRuleError("EMPTY_ORDER", "Cannot confirm an order with zero line items.")

        customer = self.db.get(Customer, so.customer_id)
        if not customer:
            raise NotFoundError(f"Customer #{so.customer_id} not found.")

        if customer.status == "inactive":
            raise BusinessRuleError(
                "CUSTOMER_INACTIVE",
                f"Cannot confirm order for inactive customer '{customer.name}'.",
            )

        # Check all products are active
        prod_ids = [item.product_id for item in so.items if item.product_id is not None]
        if prod_ids:
            inactive_prods = list(
                self.db.execute(
                    select(Product).where(Product.id.in_(prod_ids), Product.is_active == False)  # noqa: E712
                )
                .scalars()
                .all()
            )
            if inactive_prods:
                names = ", ".join(p.name for p in inactive_prods)
                raise BusinessRuleError(
                    "PRODUCT_INACTIVE",
                    f"Cannot confirm order containing inactive products: {names}",
                )

        # Roadmap Rule 7: Credit Limit Check
        if customer.credit_limit is not None and customer.credit_limit > Decimal("0.00"):
            # Uninvoiced confirmed orders amount
            uninvoiced_stmt = select(func.coalesce(func.sum(SalesOrder.grand_total), 0)).where(
                SalesOrder.customer_id == customer.id,
                SalesOrder.status == "confirmed",
                SalesOrder.id != so.id,
            )
            uninvoiced_orders_total = Decimal(str(self.db.execute(uninvoiced_stmt).scalar_one()))
            open_ar_balance = Decimal("0.00")  # In V0.3b, populated from open invoices balance_due

            total_exposure = open_ar_balance + uninvoiced_orders_total + so.grand_total
            if total_exposure > customer.credit_limit:
                raise BusinessRuleError(
                    "CREDIT_LIMIT_EXCEEDED",
                    f"Order grand total ₱{so.grand_total} causes total exposure ₱{total_exposure} "
                    f"to exceed customer credit limit ₱{customer.credit_limit}.",
                )

        # Snapshots: Billing & Shipping addresses
        b_stmt = (
            select(CustomerAddress)
            .where(
                CustomerAddress.customer_id == customer.id,
                CustomerAddress.address_type == "billing",
                CustomerAddress.is_active == True,  # noqa: E712
            )
            .order_by(CustomerAddress.is_default.desc())
        )
        billing_addr = self.db.execute(b_stmt).scalars().first()

        s_stmt = (
            select(CustomerAddress)
            .where(
                CustomerAddress.customer_id == customer.id,
                CustomerAddress.address_type == "shipping",
                CustomerAddress.is_active == True,  # noqa: E712
            )
            .order_by(CustomerAddress.is_default.desc())
        )
        shipping_addr = self.db.execute(s_stmt).scalars().first() or billing_addr

        so.billing_address_snapshot = self._format_address(billing_addr)
        so.shipping_address_snapshot = self._format_address(shipping_addr)
        so.payment_terms_days_snapshot = customer.payment_terms_days

        # Roadmap §V0.4: Reserve stock in fulfilling warehouse for physical stock items
        from app.modules.inventory.service import InventoryService

        inv_service = InventoryService(self.db, self.clock)
        inv_service.reserve_sales_order_stock(so.id)

        from_status = so.status
        so.status = "confirmed"
        so.version += 1
        so.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="sales_order",
            entity_id=so.id,
            from_status=from_status,
            to_status="confirmed",
            reason="Sales order confirmed",
            changed_by=current_user_id,
            clock=self.clock,
        )

        # Promote prospect customer to active
        if customer.status == "prospect":
            cust_from = customer.status
            customer.status = "active"
            customer.version += 1
            customer.updated_by = current_user_id
            record_status_change(
                self.db,
                entity_type="customer",
                entity_id=customer.id,
                from_status=cust_from,
                to_status="active",
                reason=f"Auto-promoted on Sales Order {so.order_no} confirmation",
                changed_by=current_user_id,
                clock=self.clock,
            )

        self.db.commit()
        self.db.refresh(so)
        return so

    def hold_sales_order(
        self,
        order_id: int,
        reason: str | None = None,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> SalesOrder:
        so = self.get_sales_order(order_id, scope_context=scope_context)
        if so.status != "confirmed":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only confirmed orders can be placed on hold. Current status: '{so.status}'",
            )

        from_status = so.status
        so.status = "on_hold"
        so.version += 1
        so.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="sales_order",
            entity_id=so.id,
            from_status=from_status,
            to_status="on_hold",
            reason=reason or "Order placed on hold",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(so)
        return so

    def release_sales_order(
        self,
        order_id: int,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> SalesOrder:
        so = self.get_sales_order(order_id, scope_context=scope_context)
        if so.status != "on_hold":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only orders on hold can be released. Current status: '{so.status}'",
            )

        from_status = so.status
        so.status = "confirmed"
        so.version += 1
        so.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="sales_order",
            entity_id=so.id,
            from_status=from_status,
            to_status="confirmed",
            reason="Order released from hold",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(so)
        return so

    def cancel_sales_order(
        self,
        order_id: int,
        reason: str | None = None,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> SalesOrder:
        so = self.get_sales_order(order_id, scope_context=scope_context)
        # Check if already shipped or invoiced (Roadmap §V0.4: cancel order blocked if shipped)
        if any(item.quantity_shipped > Decimal("0.000") for item in so.items) or so.status in (
            "partially_shipped",
            "shipped",
        ):
            raise BusinessRuleError(
                "ORDER_ALREADY_SHIPPED",
                "Cannot cancel an order that has already been partially or fully shipped.",
            )
        if any(item.quantity_invoiced > Decimal("0.000") for item in so.items):
            raise BusinessRuleError(
                "ORDER_ALREADY_INVOICED",
                "Cannot cancel an order that has already been partially or fully invoiced.",
            )

        if so.status not in ("draft", "confirmed", "on_hold"):
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Cannot cancel order in status '{so.status}'. Only draft, confirmed, or on_hold orders can be cancelled.",
            )

        from_status = so.status
        so.status = "cancelled"
        so.cancel_reason = reason
        so.version += 1
        so.updated_by = current_user_id

        # Roadmap §V0.4: If cancelling a confirmed/on-hold order, release active reservations
        if from_status in ("confirmed", "on_hold"):
            from app.modules.inventory.service import InventoryService

            inv_service = InventoryService(self.db, self.clock)
            inv_service.release_sales_order_reservations(so.id)

        record_status_change(
            self.db,
            entity_type="sales_order",
            entity_id=so.id,
            from_status=from_status,
            to_status="cancelled",
            reason=reason or "Sales order cancelled",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(so)
        return so

    # --- Invoices (Milestone V0.3b) ---

    def create_invoice_from_order(
        self,
        order_id: int,
        payload: InvoiceCreateFromOrderPayload | None = None,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Invoice:
        stmt = (
            select(SalesOrder)
            .where(SalesOrder.id == order_id)
            .options(joinedload(SalesOrder.items), joinedload(SalesOrder.customer))
        )
        if scope_context:
            stmt = apply_scope(stmt, SalesOrder, scope_context, self.db)
        so = self.db.execute(stmt).unique().scalar_one_or_none()
        if not so:
            raise NotFoundError(f"Sales order with ID {order_id} not found.")

        if so.status not in ("confirmed", "partially_shipped", "shipped"):
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Cannot create invoice from order in status '{so.status}'. Order must be 'confirmed', 'partially_shipped', or 'shipped'.",
            )

        invoice_items: list[InvoiceItem] = []
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        tax_total = Decimal("0.00")

        if payload and payload.items:
            # Custom requested items / quantities
            so_items_map = {item.id: item for item in so.items}
            for idx, req_item in enumerate(payload.items, start=1):
                if req_item.sales_order_item_id not in so_items_map:
                    raise BusinessRuleError(
                        "INVALID_ORDER_ITEM",
                        f"Order item {req_item.sales_order_item_id} does not belong to sales order {so.order_no}.",
                    )
                so_item = so_items_map[req_item.sales_order_item_id]
                remaining_qty = so_item.quantity - so_item.quantity_invoiced
                if req_item.quantity > remaining_qty:
                    raise BusinessRuleError(
                        "OVER_INVOICE_QUANTITY",
                        f"Requested quantity {req_item.quantity} exceeds remaining uninvoiced quantity {remaining_qty} for line {so_item.line_no}.",
                    )

                calc = calculate_line(
                    quantity=req_item.quantity,
                    unit_price=so_item.unit_price,
                    discount_amount=req_item.discount_amount,
                    tax_rate=so_item.tax_rate,
                )
                inv_item = InvoiceItem(
                    line_no=idx,
                    sales_order_item_id=so_item.id,
                    product_id=so_item.product_id,
                    description=req_item.description or so_item.description,
                    uom=req_item.uom or so_item.uom,
                    quantity=req_item.quantity,
                    unit_price=so_item.unit_price,
                    discount_amount=req_item.discount_amount,
                    tax_rate_id=so_item.tax_rate_id,
                    tax_rate=so_item.tax_rate,
                    line_net=calc["line_net"],
                    line_tax=calc["line_tax"],
                    line_total=calc["line_total"],
                )
                invoice_items.append(inv_item)
                subtotal += calc["line_net"]
                discount_total += req_item.discount_amount
                tax_total += calc["line_tax"]
        else:
            # Auto-populate all remaining un-invoiced items
            eligible_items = [
                item
                for item in so.items
                if item.quantity - item.quantity_invoiced > Decimal("0.000")
            ]
            if not eligible_items:
                raise BusinessRuleError(
                    "ORDER_FULLY_INVOICED",
                    f"All items on sales order {so.order_no} have already been fully invoiced.",
                )

            for idx, so_item in enumerate(eligible_items, start=1):
                qty_to_invoice = so_item.quantity - so_item.quantity_invoiced
                calc = calculate_line(
                    quantity=qty_to_invoice,
                    unit_price=so_item.unit_price,
                    discount_amount=so_item.discount_amount,
                    tax_rate=so_item.tax_rate,
                )
                inv_item = InvoiceItem(
                    line_no=idx,
                    sales_order_item_id=so_item.id,
                    product_id=so_item.product_id,
                    description=so_item.description,
                    uom=so_item.uom,
                    quantity=qty_to_invoice,
                    unit_price=so_item.unit_price,
                    discount_amount=so_item.discount_amount,
                    tax_rate_id=so_item.tax_rate_id,
                    tax_rate=so_item.tax_rate,
                    line_net=calc["line_net"],
                    line_tax=calc["line_tax"],
                    line_total=calc["line_total"],
                )
                invoice_items.append(inv_item)
                subtotal += calc["line_net"]
                discount_total += so_item.discount_amount
                tax_total += calc["line_tax"]

        subtotal = round_money(subtotal)
        discount_total = round_money(discount_total)
        tax_total = round_money(tax_total)
        grand_total = round_money(subtotal + tax_total)

        invoice = Invoice(
            customer_id=so.customer_id,
            sales_order_id=so.id,
            status="draft",
            currency_code=so.currency_code,
            subtotal=subtotal,
            discount_total=discount_total,
            tax_total=tax_total,
            grand_total=grand_total,
            amount_paid=Decimal("0.00"),
            amount_credited=Decimal("0.00"),
            balance_due=grand_total,
            items=invoice_items,
            created_by=current_user_id,
            updated_by=current_user_id,
        )

        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        record_status_change(
            self.db,
            entity_type="invoice",
            entity_id=invoice.id,
            from_status=None,
            to_status="draft",
            reason=f"Draft invoice created from Sales Order {so.order_no}",
            changed_by=current_user_id,
            clock=self.clock,
        )
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def get_invoice(self, invoice_id: int, scope_context: ScopeContext | None = None) -> Invoice:
        stmt = (
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .options(
                joinedload(Invoice.items),
                joinedload(Invoice.customer),
                joinedload(Invoice.allocations),
                joinedload(Invoice.credit_notes),
            )
        )
        if scope_context:
            stmt = apply_scope(stmt, Invoice, scope_context, self.db)
        inv = self.db.execute(stmt).unique().scalar_one_or_none()
        if not inv:
            raise NotFoundError(f"Invoice with ID {invoice_id} not found.")
        return inv

    def list_invoices(
        self,
        page: int = 1,
        page_size: int = 20,
        customer_id: int | None = None,
        status: str | None = None,
        sales_order_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> tuple[list[Invoice], int]:
        stmt = select(Invoice).options(joinedload(Invoice.items))
        if customer_id is not None:
            stmt = stmt.where(Invoice.customer_id == customer_id)
        if status is not None:
            stmt = stmt.where(Invoice.status == status)
        if sales_order_id is not None:
            stmt = stmt.where(Invoice.sales_order_id == sales_order_id)

        count_stmt = select(func.count(Invoice.id))
        if customer_id is not None:
            count_stmt = count_stmt.where(Invoice.customer_id == customer_id)
        if status is not None:
            count_stmt = count_stmt.where(Invoice.status == status)
        if sales_order_id is not None:
            count_stmt = count_stmt.where(Invoice.sales_order_id == sales_order_id)

        if scope_context:
            stmt = apply_scope(stmt, Invoice, scope_context, self.db)
            count_stmt = apply_scope(count_stmt, Invoice, scope_context, self.db)

        total = self.db.execute(count_stmt).scalar() or 0
        stmt = stmt.order_by(Invoice.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).unique().scalars().all())
        return items, total

    def issue_invoice(
        self,
        invoice_id: int,
        issue_date: date | None = None,
        due_date: date | None = None,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Invoice:
        inv = self.get_invoice(invoice_id, scope_context=scope_context)
        if inv.status != "draft":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only draft invoices can be issued. Current status: '{inv.status}'",
            )
        if not inv.items:
            raise BusinessRuleError("EMPTY_DOCUMENT", "Cannot issue an invoice with no line items.")

        customer = self.db.execute(
            select(Customer).where(Customer.id == inv.customer_id)
        ).scalar_one()

        actual_issue_date = issue_date or self.clock.now().date()
        invoice_no = generate_next_number(self.db, "invoice", self.clock)

        # Snapshots
        inv.invoice_no = invoice_no
        inv.issue_date = actual_issue_date
        inv.customer_name_snapshot = getattr(customer, "legal_name", None) or customer.name
        inv.customer_tin_snapshot = getattr(customer, "tax_id", None) or customer.tin

        # Billing address snapshot
        b_stmt = (
            select(CustomerAddress)
            .where(
                CustomerAddress.customer_id == customer.id,
                CustomerAddress.address_type == "billing",
                CustomerAddress.is_active == True,  # noqa: E712
            )
            .order_by(CustomerAddress.is_default.desc())
        )
        billing_addr = self.db.execute(b_stmt).scalars().first()
        inv.billing_address_snapshot = self._format_address(billing_addr)

        # Payment terms & Due date
        terms_days = customer.payment_terms_days or 30
        inv.due_date = due_date or (actual_issue_date + timedelta(days=terms_days))

        # Update sales order invoiced quantities and check completion
        if inv.sales_order_id:
            so = self.get_sales_order(inv.sales_order_id)
            so_items_map = {item.id: item for item in so.items}
            for inv_item in inv.items:
                if inv_item.sales_order_item_id and inv_item.sales_order_item_id in so_items_map:
                    so_item = so_items_map[inv_item.sales_order_item_id]
                    so_item.quantity_invoiced += inv_item.quantity

            # Check if all order lines are fully invoiced
            all_invoiced = all(si.quantity_invoiced >= si.quantity for si in so.items)
            all_shipped = all(si.quantity_shipped >= si.quantity for si in so.items)
            if all_invoiced:
                if so.status == "shipped" or all_shipped:
                    so_from = so.status
                    so.status = "completed"
                    so.version += 1
                    so.updated_by = current_user_id
                    record_status_change(
                        self.db,
                        entity_type="sales_order",
                        entity_id=so.id,
                        from_status=so_from,
                        to_status="completed",
                        reason=f"Order fully invoiced and shipped upon issue of Invoice {invoice_no}",
                        changed_by=current_user_id,
                        clock=self.clock,
                    )
                elif so.status == "confirmed" and all(
                    si.quantity_shipped == Decimal("0.000") for si in so.items
                ):
                    so_from = so.status
                    so.status = "completed"
                    so.version += 1
                    so.updated_by = current_user_id
                    record_status_change(
                        self.db,
                        entity_type="sales_order",
                        entity_id=so.id,
                        from_status=so_from,
                        to_status="completed",
                        reason=f"Order fully invoiced upon issue of Invoice {invoice_no}",
                        changed_by=current_user_id,
                        clock=self.clock,
                    )

        from_status = inv.status
        inv.status = "issued"
        inv.balance_due = inv.grand_total - inv.amount_paid - inv.amount_credited
        inv.version += 1
        inv.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="invoice",
            entity_id=inv.id,
            from_status=from_status,
            to_status="issued",
            reason=f"Invoice {invoice_no} officially issued",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(inv)
        return inv

    def void_invoice(
        self,
        invoice_id: int,
        reason: str | None = None,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Invoice:
        inv = self.get_invoice(invoice_id, scope_context=scope_context)
        if inv.status != "issued":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only issued invoices can be voided. Current status: '{inv.status}'",
            )
        if inv.amount_paid > Decimal("0.00"):
            raise BusinessRuleError(
                "INVOICE_HAS_PAYMENTS",
                "Cannot void invoice that has recorded payment allocations.",
            )
        if inv.amount_credited > Decimal("0.00"):
            raise BusinessRuleError(
                "INVOICE_HAS_CREDIT_NOTES",
                "Cannot void invoice that has active credit notes.",
            )

        # Reverse sales order quantity_invoiced
        if inv.sales_order_id:
            so = self.get_sales_order(inv.sales_order_id)
            so_items_map = {item.id: item for item in so.items}
            for inv_item in inv.items:
                if inv_item.sales_order_item_id and inv_item.sales_order_item_id in so_items_map:
                    so_item = so_items_map[inv_item.sales_order_item_id]
                    so_item.quantity_invoiced -= inv_item.quantity
                    if so_item.quantity_invoiced < Decimal("0.000"):
                        so_item.quantity_invoiced = Decimal("0.000")

            if so.status == "completed":
                so_from = so.status
                so.status = "confirmed"
                so.version += 1
                so.updated_by = current_user_id
                record_status_change(
                    self.db,
                    entity_type="sales_order",
                    entity_id=so.id,
                    from_status=so_from,
                    to_status="confirmed",
                    reason=f"Order reverted from completed after Invoice {inv.invoice_no} voided",
                    changed_by=current_user_id,
                    clock=self.clock,
                )

        from_status = inv.status
        inv.status = "void"
        inv.voided_at = self.clock.now()
        inv.void_reason = reason or "Voided by user"
        inv.balance_due = Decimal("0.00")
        inv.version += 1
        inv.updated_by = current_user_id

        record_status_change(
            self.db,
            entity_type="invoice",
            entity_id=inv.id,
            from_status=from_status,
            to_status="void",
            reason=reason or "Invoice voided",
            changed_by=current_user_id,
            clock=self.clock,
        )

        self.db.commit()
        self.db.refresh(inv)
        return inv

    # --- Payments & Allocations (Milestone V0.3b) ---

    def create_payment(
        self, payload: PaymentCreatePayload, current_user_id: int | None = None
    ) -> Payment:
        customer = self.db.execute(
            select(Customer).where(Customer.id == payload.customer_id)
        ).scalar_one_or_none()
        if not customer:
            raise NotFoundError(f"Customer with ID {payload.customer_id} not found.")
        if customer.status == "inactive":
            raise BusinessRuleError(
                "CUSTOMER_INACTIVE", "Cannot accept payment for inactive customer."
            )

        pay_date = payload.payment_date or self.clock.now().date()
        payment_no = generate_next_number(self.db, "payment", self.clock)

        payment = Payment(
            payment_no=payment_no,
            customer_id=payload.customer_id,
            payment_date=pay_date,
            method=payload.method,
            reference_no=payload.reference_no,
            amount=round_money(payload.amount),
            amount_allocated=Decimal("0.00"),
            status="posted",
            created_by=current_user_id,
            updated_by=current_user_id,
        )
        self.db.add(payment)
        self.db.flush()

        # If allocations are provided initially, process them
        if payload.allocations:
            for alloc_item in payload.allocations:
                self._execute_allocation(
                    payment=payment,
                    invoice_id=alloc_item.invoice_id,
                    amount=alloc_item.amount,
                    current_user_id=current_user_id,
                )

        self.db.commit()
        self.db.refresh(payment)
        return payment

    def get_payment(self, payment_id: int, scope_context: ScopeContext | None = None) -> Payment:
        stmt = (
            select(Payment)
            .where(Payment.id == payment_id)
            .options(joinedload(Payment.allocations), joinedload(Payment.customer))
        )
        if scope_context:
            stmt = apply_scope(stmt, Payment, scope_context, self.db)
        pay = self.db.execute(stmt).unique().scalar_one_or_none()
        if not pay:
            raise NotFoundError(f"Payment with ID {payment_id} not found.")
        return pay

    def list_payments(
        self,
        page: int = 1,
        page_size: int = 20,
        customer_id: int | None = None,
        status: str | None = None,
        scope_context: ScopeContext | None = None,
    ) -> tuple[list[Payment], int]:
        stmt = select(Payment).options(joinedload(Payment.allocations))
        if customer_id is not None:
            stmt = stmt.where(Payment.customer_id == customer_id)
        if status is not None:
            stmt = stmt.where(Payment.status == status)

        count_stmt = select(func.count(Payment.id))
        if customer_id is not None:
            count_stmt = count_stmt.where(Payment.customer_id == customer_id)
        if status is not None:
            count_stmt = count_stmt.where(Payment.status == status)

        if scope_context:
            stmt = apply_scope(stmt, Payment, scope_context, self.db)
            count_stmt = apply_scope(count_stmt, Payment, scope_context, self.db)

        total = self.db.execute(count_stmt).scalar() or 0
        stmt = stmt.order_by(Payment.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).unique().scalars().all())
        return items, total

    def allocate_payment(
        self,
        payment_id: int,
        invoice_id: int,
        amount: Decimal,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> PaymentAllocation:
        if scope_context:
            self.get_payment(payment_id, scope_context=scope_context)

        # Row locking payment and invoice with_for_update()
        stmt_pay = select(Payment).where(Payment.id == payment_id).with_for_update()
        pay = self.db.execute(stmt_pay).scalar_one_or_none()
        if not pay:
            raise NotFoundError(f"Payment with ID {payment_id} not found.")

        alloc = self._execute_allocation(
            payment=pay,
            invoice_id=invoice_id,
            amount=amount,
            current_user_id=current_user_id,
        )
        self.db.commit()
        return alloc

    def _execute_allocation(
        self,
        payment: Payment,
        invoice_id: int,
        amount: Decimal,
        current_user_id: int | None = None,
    ) -> PaymentAllocation:
        if amount <= Decimal("0.00"):
            raise BusinessRuleError(
                "INVALID_AMOUNT", "Allocation amount must be strictly greater than zero."
            )

        if payment.status != "posted":
            raise BusinessRuleError(
                "PAYMENT_NOT_POSTED",
                f"Cannot allocate payment with status '{payment.status}'. Payment must be 'posted'.",
            )

        # Row lock invoice
        stmt_inv = select(Invoice).where(Invoice.id == invoice_id).with_for_update()
        inv = self.db.execute(stmt_inv).scalar_one_or_none()
        if not inv:
            raise NotFoundError(f"Invoice with ID {invoice_id} not found.")

        if inv.customer_id != payment.customer_id:
            raise BusinessRuleError(
                "CUSTOMER_MISMATCH",
                "Payment customer and invoice customer must be identical.",
            )

        if inv.status not in ("issued", "partially_paid"):
            raise BusinessRuleError(
                "INVALID_INVOICE_STATUS",
                f"Cannot allocate payment to invoice with status '{inv.status}'. Must be 'issued' or 'partially_paid'.",
            )

        available_payment = payment.amount - payment.amount_allocated
        alloc_amount = round_money(amount)

        if alloc_amount > available_payment:
            raise BusinessRuleError(
                "INSUFFICIENT_PAYMENT_BALANCE",
                f"Allocation amount {alloc_amount} exceeds unallocated payment balance {available_payment}.",
            )

        if alloc_amount > inv.balance_due:
            raise BusinessRuleError(
                "OVER_ALLOCATION",
                f"Allocation amount {alloc_amount} exceeds invoice balance due {inv.balance_due}.",
            )

        # Check existing allocation pair
        stmt_existing = select(PaymentAllocation).where(
            PaymentAllocation.payment_id == payment.id,
            PaymentAllocation.invoice_id == inv.id,
        )
        alloc = self.db.execute(stmt_existing).scalar_one_or_none()
        if alloc:
            alloc.amount += alloc_amount
        else:
            alloc = PaymentAllocation(
                payment_id=payment.id,
                invoice_id=inv.id,
                amount=alloc_amount,
                allocated_at=self.clock.now(),
                allocated_by=current_user_id,
            )
            self.db.add(alloc)

        payment.amount_allocated += alloc_amount
        inv.amount_paid += alloc_amount
        inv.balance_due = round_money(inv.grand_total - inv.amount_paid - inv.amount_credited)

        from_status = inv.status
        if inv.balance_due == Decimal("0.00"):
            new_status = "paid"
        else:
            new_status = "partially_paid"

        if new_status != from_status:
            inv.status = new_status
            inv.version += 1
            inv.updated_by = current_user_id
            record_status_change(
                self.db,
                entity_type="invoice",
                entity_id=inv.id,
                from_status=from_status,
                to_status=new_status,
                reason=f"Payment {payment.payment_no} allocated {alloc_amount}",
                changed_by=current_user_id,
                clock=self.clock,
            )

        return alloc

    def void_payment(
        self,
        payment_id: int,
        reason: str | None = None,
        current_user_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> Payment:
        if scope_context:
            self.get_payment(payment_id, scope_context=scope_context)

        stmt_pay = (
            select(Payment)
            .where(Payment.id == payment_id)
            .options(joinedload(Payment.allocations))
            .with_for_update()
        )
        pay = self.db.execute(stmt_pay).unique().scalar_one_or_none()
        if not pay:
            raise NotFoundError(f"Payment with ID {payment_id} not found.")

        if pay.status != "posted":
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Only posted payments can be voided. Current status: '{pay.status}'",
            )

        # Reverse allocations on affected invoices
        for alloc in list(pay.allocations):
            stmt_inv = select(Invoice).where(Invoice.id == alloc.invoice_id).with_for_update()
            inv = self.db.execute(stmt_inv).scalar_one()

            inv.amount_paid -= alloc.amount
            if inv.amount_paid < Decimal("0.00"):
                inv.amount_paid = Decimal("0.00")
            inv.balance_due = round_money(inv.grand_total - inv.amount_paid - inv.amount_credited)

            # Revert status
            from_status = inv.status
            if inv.balance_due == inv.grand_total and inv.amount_credited == Decimal("0.00"):
                new_status = "issued"
            elif inv.balance_due > Decimal("0.00"):
                new_status = "partially_paid"
            else:
                new_status = "paid"

            if new_status != from_status:
                inv.status = new_status
                inv.version += 1
                inv.updated_by = current_user_id
                record_status_change(
                    self.db,
                    entity_type="invoice",
                    entity_id=inv.id,
                    from_status=from_status,
                    to_status=new_status,
                    reason=f"Payment {pay.payment_no} voided; allocation reversed",
                    changed_by=current_user_id,
                    clock=self.clock,
                )
            self.db.delete(alloc)

        pay.amount_allocated = Decimal("0.00")
        pay.status = "void"
        pay.void_reason = reason or "Voided by user"
        pay.version += 1
        pay.updated_by = current_user_id

        self.db.commit()
        self.db.refresh(pay)
        return pay

    # --- Credit Notes (Milestone V0.3b) ---

    def create_credit_note(
        self, payload: CreditNoteCreatePayload, current_user_id: int | None = None
    ) -> CreditNote:
        inv = self.get_invoice(payload.invoice_id)
        if inv.status not in ("issued", "partially_paid", "paid"):
            raise BusinessRuleError(
                "INVALID_INVOICE_STATUS",
                f"Cannot issue credit note against invoice in status '{inv.status}'.",
            )

        credit_items: list[CreditNoteItem] = []
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        tax_total = Decimal("0.00")

        if payload.items:
            inv_items_map = {item.id: item for item in inv.items}
            for idx, item_data in enumerate(payload.items, start=1):
                inv_item = (
                    inv_items_map.get(item_data.invoice_item_id)
                    if item_data.invoice_item_id
                    else None
                )
                tax_rate_val = inv_item.tax_rate if inv_item else Decimal("0.1200")
                tax_rate_id_val = inv_item.tax_rate_id if inv_item else 1

                calc = calculate_line(
                    quantity=item_data.quantity,
                    unit_price=item_data.unit_price,
                    discount_amount=item_data.discount_amount,
                    tax_rate=tax_rate_val,
                )
                cn_item = CreditNoteItem(
                    line_no=idx,
                    invoice_item_id=inv_item.id if inv_item else None,
                    product_id=item_data.product_id or (inv_item.product_id if inv_item else None),
                    description=item_data.description
                    or (inv_item.description if inv_item else f"Credit item {idx}"),
                    uom=item_data.uom or (inv_item.uom if inv_item else "pc"),
                    quantity=item_data.quantity,
                    unit_price=item_data.unit_price,
                    discount_amount=item_data.discount_amount,
                    tax_rate_id=tax_rate_id_val,
                    tax_rate=tax_rate_val,
                    line_net=calc["line_net"],
                    line_tax=calc["line_tax"],
                    line_total=calc["line_total"],
                )
                credit_items.append(cn_item)
                subtotal += calc["line_net"]
                discount_total += item_data.discount_amount
                tax_total += calc["line_tax"]
        else:
            # Default full remaining balance
            if inv.balance_due <= Decimal("0.00"):
                raise BusinessRuleError(
                    "INVOICE_ZERO_BALANCE",
                    "Invoice has zero remaining balance due to credit.",
                )
            default_tax = self.get_default_tax_rate()
            # Pro-rate net and tax from balance due
            # Or use balance due directly with 0 tax line
            zero_tax = (
                self.db.execute(select(TaxRate).where(TaxRate.rate == Decimal("0.0000")))
                .scalars()
                .first()
                or default_tax
            )
            calc = calculate_line(
                quantity=Decimal("1.000"),
                unit_price=inv.balance_due,
                discount_amount=Decimal("0.00"),
                tax_rate=zero_tax.rate,
            )
            cn_item = CreditNoteItem(
                line_no=1,
                invoice_item_id=None,
                product_id=None,
                description=f"Credit note balance adjustment for Invoice {inv.invoice_no}",
                uom="ea",
                quantity=Decimal("1.000"),
                unit_price=inv.balance_due,
                discount_amount=Decimal("0.00"),
                tax_rate_id=zero_tax.id,
                tax_rate=zero_tax.rate,
                line_net=calc["line_net"],
                line_tax=calc["line_tax"],
                line_total=calc["line_total"],
            )
            credit_items.append(cn_item)
            subtotal = calc["line_net"]
            tax_total = calc["line_tax"]

        subtotal = round_money(subtotal)
        discount_total = round_money(discount_total)
        tax_total = round_money(tax_total)
        grand_total = round_money(subtotal + tax_total)

        max_allowed_credit = inv.grand_total - inv.amount_credited
        if grand_total > max_allowed_credit:
            raise BusinessRuleError(
                "EXCESSIVE_CREDIT",
                f"Credit note amount {grand_total} exceeds maximum creditable amount {max_allowed_credit}.",
            )

        if grand_total > inv.balance_due:
            raise BusinessRuleError(
                "EXCEEDS_BALANCE_DUE",
                f"Credit note amount {grand_total} exceeds current balance due {inv.balance_due}.",
            )

        actual_issue_date = self.clock.now().date()
        cn_no = generate_next_number(self.db, "credit_note", self.clock)

        credit_note = CreditNote(
            credit_note_no=cn_no,
            invoice_id=inv.id,
            customer_id=inv.customer_id,
            status="issued",
            issue_date=actual_issue_date,
            reason=payload.reason,
            currency_code=inv.currency_code,
            subtotal=subtotal,
            discount_total=discount_total,
            tax_total=tax_total,
            grand_total=grand_total,
            items=credit_items,
            created_by=current_user_id,
            updated_by=current_user_id,
        )
        self.db.add(credit_note)

        # Apply credit to invoice
        inv.amount_credited += grand_total
        inv.balance_due = round_money(inv.grand_total - inv.amount_paid - inv.amount_credited)

        from_status = inv.status
        if inv.balance_due == Decimal("0.00"):
            new_status = "paid"
            if new_status != from_status:
                inv.status = new_status
                inv.version += 1
                inv.updated_by = current_user_id
                record_status_change(
                    self.db,
                    entity_type="invoice",
                    entity_id=inv.id,
                    from_status=from_status,
                    to_status=new_status,
                    reason=f"Settled by Credit Note {cn_no}",
                    changed_by=current_user_id,
                    clock=self.clock,
                )

        self.db.commit()
        self.db.refresh(credit_note)
        return credit_note

    def get_credit_note(
        self, credit_note_id: int, scope_context: ScopeContext | None = None
    ) -> CreditNote:
        stmt = (
            select(CreditNote)
            .where(CreditNote.id == credit_note_id)
            .options(joinedload(CreditNote.items), joinedload(CreditNote.customer))
        )
        if scope_context:
            stmt = apply_scope(stmt, CreditNote, scope_context, self.db)
        cn = self.db.execute(stmt).unique().scalar_one_or_none()
        if not cn:
            raise NotFoundError(f"Credit note with ID {credit_note_id} not found.")
        return cn

    def list_credit_notes(
        self,
        page: int = 1,
        page_size: int = 20,
        customer_id: int | None = None,
        invoice_id: int | None = None,
        scope_context: ScopeContext | None = None,
    ) -> tuple[list[CreditNote], int]:
        stmt = select(CreditNote).options(joinedload(CreditNote.items))
        if customer_id is not None:
            stmt = stmt.where(CreditNote.customer_id == customer_id)
        if invoice_id is not None:
            stmt = stmt.where(CreditNote.invoice_id == invoice_id)

        count_stmt = select(func.count(CreditNote.id))
        if customer_id is not None:
            count_stmt = count_stmt.where(CreditNote.customer_id == customer_id)
        if invoice_id is not None:
            count_stmt = count_stmt.where(CreditNote.invoice_id == invoice_id)

        if scope_context:
            stmt = apply_scope(stmt, CreditNote, scope_context, self.db)
            count_stmt = apply_scope(count_stmt, CreditNote, scope_context, self.db)

        total = self.db.execute(count_stmt).scalar() or 0
        stmt = stmt.order_by(CreditNote.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).unique().scalars().all())
        return items, total

    # --- Customer Statement (Milestone V0.3b) ---

    def get_customer_statement(
        self, customer_id: int, scope_context: ScopeContext | None = None
    ) -> CustomerStatementOut:
        cust_stmt = select(Customer).where(Customer.id == customer_id)
        if scope_context:
            cust_stmt = apply_scope(cust_stmt, Customer, scope_context, self.db)
        customer = self.db.execute(cust_stmt).scalar_one_or_none()
        if not customer:
            raise NotFoundError(f"Customer with ID {customer_id} not found.")

        # Invoices
        inv_stmt = (
            select(Invoice)
            .where(Invoice.customer_id == customer_id, Invoice.status.notin_(["draft", "void"]))
            .order_by(Invoice.issue_date.asc(), Invoice.id.asc())
        )
        invoices = list(self.db.execute(inv_stmt).scalars().all())

        # Payments
        pay_stmt = (
            select(Payment)
            .where(Payment.customer_id == customer_id, Payment.status != "void")
            .order_by(Payment.payment_date.asc(), Payment.id.asc())
        )
        payments = list(self.db.execute(pay_stmt).scalars().all())

        # Credit Notes
        cn_stmt = (
            select(CreditNote)
            .where(CreditNote.customer_id == customer_id, CreditNote.status != "void")
            .order_by(CreditNote.issue_date.asc(), CreditNote.id.asc())
        )
        credit_notes = list(self.db.execute(cn_stmt).scalars().all())

        total_invoiced = sum(i.grand_total for i in invoices)
        total_paid = sum(p.amount for p in payments)
        total_credited = sum(c.grand_total for c in credit_notes)
        unallocated_credit = sum(p.amount - p.amount_allocated for p in payments)
        open_ar_balance = sum(i.balance_due for i in invoices) - unallocated_credit

        # Build chronological transactions ledger
        raw_events: list[dict[str, Any]] = []
        for i in invoices:
            raw_events.append(
                {
                    "date": i.issue_date or i.created_at.date(),
                    "doc_type": "invoice",
                    "doc_no": i.invoice_no or f"INV-{i.id}",
                    "reference": f"Due {i.due_date}" if i.due_date else None,
                    "invoiced": i.grand_total,
                    "paid": Decimal("0.00"),
                }
            )
        for p in payments:
            raw_events.append(
                {
                    "date": p.payment_date,
                    "doc_type": "payment",
                    "doc_no": p.payment_no,
                    "reference": p.reference_no,
                    "invoiced": Decimal("0.00"),
                    "paid": p.amount,
                }
            )
        for c in credit_notes:
            raw_events.append(
                {
                    "date": c.issue_date or c.created_at.date(),
                    "doc_type": "credit_note",
                    "doc_no": c.credit_note_no or f"CN-{c.id}",
                    "reference": c.reason,
                    "invoiced": Decimal("0.00"),
                    "paid": c.grand_total,
                }
            )

        raw_events.sort(key=lambda x: (x["date"], x["doc_no"]))

        running = Decimal("0.00")
        txns: list[StatementTransactionOut] = []
        for ev in raw_events:
            running += ev["invoiced"] - ev["paid"]
            txns.append(
                StatementTransactionOut(
                    date=ev["date"],
                    doc_type=ev["doc_type"],
                    doc_no=ev["doc_no"],
                    reference=ev["reference"],
                    amount_invoiced=str(ev["invoiced"]),
                    amount_paid=str(ev["paid"]),
                    running_balance=str(round_money(running)),
                )
            )

        return CustomerStatementOut(
            customer_id=customer.id,
            customer_name=customer.name,
            statement_date=self.clock.now().date(),
            total_invoiced=str(round_money(total_invoiced)),
            total_paid=str(round_money(total_paid)),
            total_credited=str(round_money(total_credited)),
            unallocated_credit=str(round_money(unallocated_credit)),
            open_ar_balance=str(round_money(open_ar_balance)),
            transactions=txns,
        )

    # --- Idempotency Support (Milestone V0.3b) ---

    def check_idempotency(
        self, user_id: int, key: str, request_hash: str
    ) -> tuple[bool, int | None, Any | None]:
        stmt = select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
        )
        existing = self.db.execute(stmt).scalar_one_or_none()
        if not existing:
            return False, None, None

        if existing.request_hash != request_hash:
            raise AppException(
                status_code=422,
                code="IDEMPOTENCY_CONFLICT",
                title="Unprocessable Entity",
                detail="Idempotency key was previously used with a different request payload.",
            )

        if existing.response_status is not None and existing.response_body is not None:
            return True, existing.response_status, json.loads(existing.response_body)

        raise ConflictError("A request with this idempotency key is already in progress.")

    def record_idempotency_result(
        self,
        user_id: int,
        key: str,
        method: str,
        path: str,
        request_hash: str,
        status_code: int,
        response_body: Any,
    ) -> None:
        stmt = select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
        )
        existing = self.db.execute(stmt).scalar_one_or_none()
        body_str = json.dumps(response_body, default=str)
        if existing:
            existing.response_status = status_code
            existing.response_body = body_str
        else:
            new_key = IdempotencyKey(
                user_id=user_id,
                key=key,
                method=method,
                path=path,
                request_hash=request_hash,
                response_status=status_code,
                response_body=body_str,
                created_at=self.clock.now(),
            )
            self.db.add(new_key)
        self.db.commit()
