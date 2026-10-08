from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.clock import Clock, get_clock
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.money import calculate_line, round_money
from app.core.numbering import generate_next_number
from app.core.status_history import record_status_change
from app.modules.catalog.models import Product
from app.modules.crm.models import Customer, CustomerAddress, Opportunity
from app.modules.sales.models import Quote, QuoteItem, SalesOrder, SalesOrderItem, TaxRate
from app.modules.sales.schemas import (
    LineItemPayload,
    QuoteCreatePayload,
    QuoteUpdatePayload,
    SalesOrderCreatePayload,
    SalesOrderUpdatePayload,
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

    def create_quote(self, payload: QuoteCreatePayload, current_user_id: int | None = None) -> Quote:
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

    def get_quote(self, quote_id: int) -> Quote:
        stmt = (
            select(Quote)
            .options(joinedload(Quote.items))
            .where(Quote.id == quote_id)
        )
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
    ) -> tuple[list[Quote], int]:
        stmt = select(Quote).options(joinedload(Quote.items))
        count_stmt = select(func.count(Quote.id))

        if customer_id:
            stmt = stmt.where(Quote.customer_id == customer_id)
            count_stmt = count_stmt.where(Quote.customer_id == customer_id)
        if status:
            stmt = stmt.where(Quote.status == status)
            count_stmt = count_stmt.where(Quote.status == status)

        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(Quote.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).unique().scalars().all())
        return items, total

    def update_quote(
        self, quote_id: int, payload: QuoteUpdatePayload, current_user_id: int | None = None
    ) -> Quote:
        quote = self.get_quote(quote_id)
        if quote.status != "draft":
            raise BusinessRuleError(
                "QUOTE_IMMUTABLE", f"Cannot edit quote in status '{quote.status}'. Only drafts are editable."
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

    def send_quote(self, quote_id: int, current_user_id: int | None = None) -> Quote:
        quote = self.get_quote(quote_id)
        if quote.status != "draft":
            raise BusinessRuleError(
                "INVALID_TRANSITION", f"Only draft quotes can be sent. Current status: '{quote.status}'"
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

    def accept_quote(self, quote_id: int, current_user_id: int | None = None) -> Quote:
        quote = self.get_quote(quote_id)
        if quote.status != "sent":
            raise BusinessRuleError(
                "INVALID_TRANSITION", f"Only sent quotes can be accepted. Current status: '{quote.status}'"
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
        self, quote_id: int, reason: str | None = None, current_user_id: int | None = None
    ) -> Quote:
        quote = self.get_quote(quote_id)
        if quote.status != "sent":
            raise BusinessRuleError(
                "INVALID_TRANSITION", f"Only sent quotes can be rejected. Current status: '{quote.status}'"
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
        self, quote_id: int, reason: str | None = None, current_user_id: int | None = None
    ) -> Quote:
        quote = self.get_quote(quote_id)
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
        self, quote_id: int, current_user_id: int | None = None
    ) -> SalesOrder:
        """Roadmap Rule 5: Creates Sales Order directly from accepted (or sent) quote, copying lines and preserving snapshots."""
        quote = self.get_quote(quote_id)
        if quote.status not in ("accepted", "sent"):
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Cannot create order from quote in status '{quote.status}'. Quote must be sent or accepted.",
            )

        if not quote.items:
            raise BusinessRuleError("EMPTY_ORDER", "Quote has no line items.")

        order_no = generate_next_number(self.db, "sales_order", self.clock)

        so = SalesOrder(
            order_no=order_no,
            customer_id=quote.customer_id,
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

        so = SalesOrder(
            order_no=order_no,
            customer_id=payload.customer_id,
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

    def get_sales_order(self, order_id: int) -> SalesOrder:
        stmt = (
            select(SalesOrder)
            .options(joinedload(SalesOrder.items))
            .where(SalesOrder.id == order_id)
        )
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
    ) -> tuple[list[SalesOrder], int]:
        stmt = select(SalesOrder).options(joinedload(SalesOrder.items))
        count_stmt = select(func.count(SalesOrder.id))

        if customer_id:
            stmt = stmt.where(SalesOrder.customer_id == customer_id)
            count_stmt = count_stmt.where(SalesOrder.customer_id == customer_id)
        if status:
            stmt = stmt.where(SalesOrder.status == status)
            count_stmt = count_stmt.where(SalesOrder.status == status)

        total = self.db.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(SalesOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list(self.db.execute(stmt).unique().scalars().all())
        return items, total

    def update_sales_order(
        self, order_id: int, payload: SalesOrderUpdatePayload, current_user_id: int | None = None
    ) -> SalesOrder:
        so = self.get_sales_order(order_id)
        if so.status != "draft":
            raise BusinessRuleError(
                "ORDER_IMMUTABLE", f"Cannot edit order in status '{so.status}'. Only drafts are editable."
            )
        if so.version != payload.version:
            raise ConflictError("Sales order was modified by another transaction. Please reload.")

        default_tr = self.get_default_tax_rate()
        so_items, subtotal, discount_total, tax_total, grand_total = self._prepare_so_items(
            payload.items, default_tr
        )

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
        self, order_id: int, current_user_id: int | None = None
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
        so = self.get_sales_order(order_id)
        if so.status != "draft":
            raise BusinessRuleError(
                "INVALID_TRANSITION", f"Only draft orders can be confirmed. Current status: '{so.status}'"
            )

        if not so.items:
            raise BusinessRuleError("EMPTY_ORDER", "Cannot confirm an order with zero line items.")

        customer = self.db.get(Customer, so.customer_id)
        if not customer:
            raise NotFoundError(f"Customer #{so.customer_id} not found.")

        if customer.status == "inactive":
            raise BusinessRuleError(
                "CUSTOMER_INACTIVE", f"Cannot confirm order for inactive customer '{customer.name}'."
            )

        # Check all products are active
        prod_ids = [item.product_id for item in so.items if item.product_id is not None]
        if prod_ids:
            inactive_prods = list(
                self.db.execute(
                    select(Product).where(Product.id.in_(prod_ids), Product.is_active == False)  # noqa: E712
                ).scalars().all()
            )
            if inactive_prods:
                names = ", ".join(p.name for p in inactive_prods)
                raise BusinessRuleError(
                    "PRODUCT_INACTIVE", f"Cannot confirm order containing inactive products: {names}"
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
        b_stmt = select(CustomerAddress).where(
            CustomerAddress.customer_id == customer.id,
            CustomerAddress.address_type == "billing",
            CustomerAddress.is_active == True,  # noqa: E712
        ).order_by(CustomerAddress.is_default.desc())
        billing_addr = self.db.execute(b_stmt).scalars().first()

        s_stmt = select(CustomerAddress).where(
            CustomerAddress.customer_id == customer.id,
            CustomerAddress.address_type == "shipping",
            CustomerAddress.is_active == True,  # noqa: E712
        ).order_by(CustomerAddress.is_default.desc())
        shipping_addr = self.db.execute(s_stmt).scalars().first() or billing_addr

        so.billing_address_snapshot = self._format_address(billing_addr)
        so.shipping_address_snapshot = self._format_address(shipping_addr)
        so.payment_terms_days_snapshot = customer.payment_terms_days

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
        self, order_id: int, reason: str | None = None, current_user_id: int | None = None
    ) -> SalesOrder:
        so = self.get_sales_order(order_id)
        if so.status != "confirmed":
            raise BusinessRuleError(
                "INVALID_TRANSITION", f"Only confirmed orders can be placed on hold. Current status: '{so.status}'"
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

    def release_sales_order(self, order_id: int, current_user_id: int | None = None) -> SalesOrder:
        so = self.get_sales_order(order_id)
        if so.status != "on_hold":
            raise BusinessRuleError(
                "INVALID_TRANSITION", f"Only orders on hold can be released. Current status: '{so.status}'"
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
        self, order_id: int, reason: str | None = None, current_user_id: int | None = None
    ) -> SalesOrder:
        so = self.get_sales_order(order_id)
        if so.status not in ("draft", "confirmed", "on_hold"):
            raise BusinessRuleError(
                "INVALID_TRANSITION",
                f"Cannot cancel order in status '{so.status}'. Only draft, confirmed, or on_hold orders can be cancelled.",
            )

        # If confirmed or on_hold, check nothing has been invoiced
        if any(item.quantity_invoiced > Decimal("0.000") for item in so.items):
            raise BusinessRuleError(
                "ORDER_ALREADY_INVOICED", "Cannot cancel an order that has already been partially or fully invoiced."
            )

        from_status = so.status
        so.status = "cancelled"
        so.cancel_reason = reason
        so.version += 1
        so.updated_by = current_user_id

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
