"""Scheduled Business Checks Engine (Roadmap §V1.8)

Executes daily scheduled checks:
1. Daily: invoices past due -> enqueues sales.invoice_past_due
2. Daily: quotes past valid_until -> enqueues sales.quote_expired
3. Daily: opportunities closing in 7 days -> enqueues crm.opportunity_closing_soon
4. Daily: POs past expected_date not received -> enqueues purchasing.po_delayed
5. Inventory below reorder point -> enqueues inventory.below_reorder
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import get_clock
from app.modules.catalog.models import Product
from app.modules.crm.models import Opportunity
from app.modules.events.service import OutboxService
from app.modules.inventory.models import InventoryBalance
from app.modules.purchasing.models import PurchaseOrder
from app.modules.sales.models import Invoice, Quote


class ScheduledChecksEngine:
    """Orchestrates daily scheduled business rule checks and enqueues outbox events."""

    @classmethod
    def check_invoices_past_due(cls, db: Session) -> int:
        """Finds overdue invoices and enqueues notification events."""
        clock = get_clock()
        today = clock.now().date()
        stmt = select(Invoice).where(
            Invoice.status.in_(["issued", "partially_paid"]),
            Invoice.due_date.is_not(None),
            Invoice.due_date < today,
            Invoice.balance_due > Decimal("0.00"),
        )
        invoices = list(db.execute(stmt).scalars().all())
        count = 0
        for inv in invoices:
            OutboxService.record_event(
                db=db,
                event_type="sales.invoice_past_due",
                aggregate_type="invoice",
                aggregate_id=inv.id,
                payload={
                    "invoice_id": inv.id,
                    "invoice_no": inv.invoice_no,
                    "customer_id": inv.customer_id,
                    "customer_name": inv.customer.name if inv.customer else "Customer",
                    "balance_due": str(inv.balance_due),
                    "due_date": inv.due_date.isoformat() if inv.due_date else None,
                    "owner_id": inv.created_by,
                    "customer_email": inv.customer.email if inv.customer else None,
                },
            )
            count += 1
        return count

    @classmethod
    def check_quotes_expired(cls, db: Session) -> int:
        """Finds quotes past valid_until and enqueues expiration events."""
        clock = get_clock()
        today = clock.now().date()
        stmt = select(Quote).where(
            Quote.status == "sent",
            Quote.valid_until.is_not(None),
            Quote.valid_until < today,
        )
        quotes = list(db.execute(stmt).scalars().all())
        count = 0
        for q in quotes:
            OutboxService.record_event(
                db=db,
                event_type="sales.quote_expired",
                aggregate_type="quote",
                aggregate_id=q.id,
                payload={
                    "quote_id": q.id,
                    "quote_no": q.quote_no,
                    "valid_until": q.valid_until.isoformat() if q.valid_until else None,
                },
            )
            count += 1
        return count

    @classmethod
    def check_opportunities_closing_soon(cls, db: Session) -> int:
        """Finds opportunities closing within the next 7 days and enqueues reminders."""
        clock = get_clock()
        today = clock.now().date()
        horizon = today + timedelta(days=7)
        stmt = select(Opportunity).where(
            Opportunity.stage.notin_(["won", "lost"]),
            Opportunity.expected_close_date.is_not(None),
            Opportunity.expected_close_date >= today,
            Opportunity.expected_close_date <= horizon,
        )
        opps = list(db.execute(stmt).scalars().all())
        count = 0
        for opp in opps:
            days_remaining = (
                (opp.expected_close_date - today).days if opp.expected_close_date else 0
            )
            OutboxService.record_event(
                db=db,
                event_type="crm.opportunity_closing_soon",
                aggregate_type="opportunity",
                aggregate_id=opp.id,
                payload={
                    "opportunity_id": opp.id,
                    "opportunity_no": opp.opportunity_no,
                    "name": opp.name,
                    "owner_id": opp.owner_user_id or opp.created_by,
                    "days_remaining": days_remaining,
                    "estimated_amount": str(opp.estimated_amount),
                },
            )
            count += 1
        return count

    @classmethod
    def check_purchase_orders_delayed(cls, db: Session) -> int:
        """Finds POs past expected delivery date and enqueues delayed alerts."""
        clock = get_clock()
        today = clock.now().date()
        stmt = select(PurchaseOrder).where(
            PurchaseOrder.status.in_(["sent", "partially_received"]),
            PurchaseOrder.expected_date.is_not(None),
            PurchaseOrder.expected_date < today,
        )
        pos = list(db.execute(stmt).scalars().all())
        count = 0
        for po in pos:
            OutboxService.record_event(
                db=db,
                event_type="purchasing.po_delayed",
                aggregate_type="purchase_order",
                aggregate_id=po.id,
                payload={
                    "po_id": po.id,
                    "po_no": po.po_no,
                    "supplier_name": po.supplier.name if po.supplier else "Supplier",
                    "expected_date": po.expected_date.isoformat() if po.expected_date else None,
                },
            )
            count += 1
        return count

    @classmethod
    def check_inventory_below_reorder(cls, db: Session) -> int:
        """Finds inventory products below reorder point and enqueues alerts."""
        stmt = select(Product).where(
            Product.product_type == "stock",
            Product.is_active.is_(True),
            Product.reorder_point > Decimal("0.00"),
        )
        products = list(db.execute(stmt).scalars().all())
        count = 0
        for prod in products:
            items_stmt = select(InventoryBalance).where(InventoryBalance.product_id == prod.id)
            items = list(db.execute(items_stmt).scalars().all())
            total_qty = sum((i.qty_on_hand for i in items), Decimal("0.000"))
            if total_qty <= prod.reorder_point:
                OutboxService.record_event(
                    db=db,
                    event_type="inventory.below_reorder",
                    aggregate_type="product",
                    aggregate_id=prod.id,
                    payload={
                        "product_id": prod.id,
                        "product_name": prod.name,
                        "sku": prod.sku,
                        "qty_on_hand": float(total_qty),
                        "reorder_point": float(prod.reorder_point),
                    },
                )
                count += 1
        return count

    @classmethod
    def run_all_scheduled_checks(cls, db: Session) -> dict[str, int]:
        """Runs all 5 scheduled checks in one atomic operation."""
        results = {
            "invoices_past_due": cls.check_invoices_past_due(db),
            "quotes_expired": cls.check_quotes_expired(db),
            "opportunities_closing_soon": cls.check_opportunities_closing_soon(db),
            "pos_delayed": cls.check_purchase_orders_delayed(db),
            "inventory_below_reorder": cls.check_inventory_below_reorder(db),
        }
        db.commit()
        return results
