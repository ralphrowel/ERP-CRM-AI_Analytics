from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext, apply_scope
from app.modules.catalog.models import Product, ProductCategory
from app.modules.crm.models import Customer, Lead, Opportunity
from app.modules.inventory.models import (
    InventoryBalance,
    Shipment,
    ShipmentItem,
    Warehouse,
)
from app.modules.purchasing.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierInvoice,
)
from app.modules.reporting.schemas import (
    ARAgingBucket,
    ARAgingCustomerRow,
    ARAgingResponse,
    ExecutiveSummaryResponse,
    InventoryReportResponse,
    KPICard,
    LowStockItemRow,
    PipelineReportResponse,
    PipelineStageSummary,
    ProcurementReportResponse,
    RevenueMarginMonthlyPoint,
    RevenueReportResponse,
    SupplierSpendRow,
    WarehouseInventorySummary,
)
from app.modules.sales.models import (
    CreditNote,
    Invoice,
    SalesOrder,
)


class ReportingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _get_scoped_customer_ids(self, context: ScopeContext) -> set[int] | None:
        """Returns customer IDs accessible to the current user, or None if scope is 'all'."""
        if context.user.is_superuser or context.scope == "all":
            return None

        q = select(Customer.id)
        q = apply_scope(q, Customer, context, self.db)
        return set(self.db.execute(q).scalars().all())

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Executive Summary & Scorecards (KPI-001 through KPI-018)
    # ──────────────────────────────────────────────────────────────────────────
    def get_executive_summary(
        self,
        context: ScopeContext,
        period_start: date | None = None,
        period_end: date | None = None,
        as_of_date: date | None = None,
    ) -> ExecutiveSummaryResponse:
        today = as_of_date or date.today()
        # Default period: Current Month to Date
        start = period_start or today.replace(day=1)
        end = period_end or today

        scoped_customer_ids = self._get_scoped_customer_ids(context)

        # KPI-001: Net Revenue
        inv_q = select(func.coalesce(func.sum(Invoice.subtotal), Decimal("0.00"))).where(
            Invoice.status.in_(["issued", "partially_paid", "paid"]),
            Invoice.issue_date >= start,
            Invoice.issue_date <= end,
        )
        cn_q = select(func.coalesce(func.sum(CreditNote.subtotal), Decimal("0.00"))).where(
            CreditNote.status == "issued",
            CreditNote.issue_date >= start,
            CreditNote.issue_date <= end,
        )
        if scoped_customer_ids is not None:
            inv_q = inv_q.where(Invoice.customer_id.in_(scoped_customer_ids))
            cn_q = cn_q.where(CreditNote.customer_id.in_(scoped_customer_ids))

        inv_subtotal = Decimal(str(self.db.execute(inv_q).scalar_one()))
        cn_subtotal = Decimal(str(self.db.execute(cn_q).scalar_one()))
        net_revenue = inv_subtotal - cn_subtotal

        # KPI-002 & KPI-003: COGS and Gross Margin
        dt_start = datetime.combine(start, time.min, tzinfo=timezone.utc)
        dt_end = datetime.combine(end, time.max, tzinfo=timezone.utc)
        cogs_q = (
            select(func.coalesce(func.sum(ShipmentItem.cogs_amount), Decimal("0.00")))
            .join(Shipment, Shipment.id == ShipmentItem.shipment_id)
            .where(
                Shipment.status == "posted",
                Shipment.shipped_at >= dt_start,
                Shipment.shipped_at <= dt_end,
            )
        )
        cogs = Decimal(str(self.db.execute(cogs_q).scalar_one()))
        gross_margin = net_revenue - cogs
        gross_margin_pct = (
            (gross_margin / net_revenue * Decimal("100")).quantize(Decimal("0.01"))
            if net_revenue > Decimal("0.00")
            else Decimal("0.00")
        )

        # KPI-004: Confirmed Orders
        so_q = select(func.count(SalesOrder.id)).where(
            SalesOrder.status.in_(["confirmed", "processing", "completed"]),
            SalesOrder.order_date >= start,
            SalesOrder.order_date <= end,
        )
        if scoped_customer_ids is not None:
            so_q = so_q.where(SalesOrder.customer_id.in_(scoped_customer_ids))
        confirmed_orders = int(self.db.execute(so_q).scalar_one())

        # KPI-005: AR Outstanding
        ar_q = select(func.coalesce(func.sum(Invoice.balance_due), Decimal("0.00"))).where(
            Invoice.status.in_(["issued", "partially_paid"]),
            Invoice.issue_date <= today,
        )
        if scoped_customer_ids is not None:
            ar_q = ar_q.where(Invoice.customer_id.in_(scoped_customer_ids))
        ar_outstanding = Decimal(str(self.db.execute(ar_q).scalar_one()))

        # KPI-007: Weighted Pipeline
        opp_q = select(
            func.coalesce(
                func.sum(Opportunity.estimated_amount * Opportunity.probability),
                Decimal("0.00"),
            )
        ).where(
            Opportunity.stage.notin_(["won", "lost"]),
        )
        opp_q = apply_scope(opp_q, Opportunity, context, self.db)
        weighted_pipeline = Decimal(str(self.db.execute(opp_q).scalar_one())).quantize(
            Decimal("0.01")
        )

        # KPI-008: Win Rate
        closed_opps_q = select(
            func.count(Opportunity.id),
            func.count(case((Opportunity.stage == "won", 1))),
        ).where(
            Opportunity.stage.in_(["won", "lost"]),
            Opportunity.closed_at >= dt_start,
            Opportunity.closed_at <= dt_end,
        )
        closed_opps_q = apply_scope(closed_opps_q, Opportunity, context, self.db)
        total_closed, total_won = self.db.execute(closed_opps_q).fetchone() or (0, 0)
        win_rate = (
            Decimal(str((total_won / total_closed) * 100)).quantize(Decimal("0.01"))
            if total_closed > 0
            else Decimal("0.00")
        )

        # KPI-013: Inventory Value
        inv_val_q = select(
            func.coalesce(
                func.sum(InventoryBalance.qty_on_hand * InventoryBalance.avg_unit_cost),
                Decimal("0.00"),
            )
        )
        inventory_value = Decimal(str(self.db.execute(inv_val_q).scalar_one())).quantize(
            Decimal("0.01")
        )

        # KPI-015: Low-Stock Items
        low_stock_q = (
            select(func.count(Product.id))
            .join(InventoryBalance, InventoryBalance.product_id == Product.id, isouter=True)
            .where(
                Product.is_active == True,  # noqa: E712
                Product.product_type == "stock",
                Product.reorder_point > 0,
            )
            .group_by(Product.id, Product.reorder_point)
            .having(
                func.coalesce(
                    func.sum(InventoryBalance.qty_on_hand - InventoryBalance.qty_reserved),
                    Decimal("0.000"),
                )
                < Product.reorder_point
            )
        )
        low_stock_count = len(self.db.execute(low_stock_q).scalars().all())

        # KPI-016: Purchase Spend
        po_spend_q = select(
            func.coalesce(func.sum(SupplierInvoice.subtotal), Decimal("0.00"))
        ).where(
            SupplierInvoice.status.in_(["approved", "partially_paid", "paid"]),
            SupplierInvoice.invoice_date >= start,
            SupplierInvoice.invoice_date <= end,
        )
        purchase_spend = Decimal(str(self.db.execute(po_spend_q).scalar_one()))

        # KPI-018: Days Sales Outstanding (DSO)
        t90_start = today - timedelta(days=90)
        t90_inv_q = select(func.coalesce(func.sum(Invoice.subtotal), Decimal("0.00"))).where(
            Invoice.status.in_(["issued", "partially_paid", "paid"]),
            Invoice.issue_date >= t90_start,
            Invoice.issue_date <= today,
        )
        if scoped_customer_ids is not None:
            t90_inv_q = t90_inv_q.where(Invoice.customer_id.in_(scoped_customer_ids))
        t90_revenue = Decimal(str(self.db.execute(t90_inv_q).scalar_one()))
        daily_rev = t90_revenue / Decimal("90") if t90_revenue > 0 else Decimal("0.00")
        dso_days = (
            (ar_outstanding / daily_rev).quantize(Decimal("0.1"))
            if daily_rev > 0
            else None
        )

        scorecards = [
            KPICard(
                kpi_id="KPI-001",
                kpi_name="Net Revenue",
                domain="Finance / Sales",
                value=net_revenue,
                formatted_value=f"₱{net_revenue:,.2f}",
                unit="PHP",
                trend="up" if net_revenue > 0 else "neutral",
            ),
            KPICard(
                kpi_id="KPI-002",
                kpi_name="Gross Margin",
                domain="Finance / Operations",
                value=gross_margin,
                formatted_value=f"₱{gross_margin:,.2f}",
                unit="PHP",
                trend="up" if gross_margin > 0 else "neutral",
            ),
            KPICard(
                kpi_id="KPI-003",
                kpi_name="Gross Margin %",
                domain="Executive Management",
                value=gross_margin_pct,
                formatted_value=f"{gross_margin_pct:.1f}%",
                unit="%",
                trend="up" if gross_margin_pct >= Decimal("25.0") else "neutral",
            ),
            KPICard(
                kpi_id="KPI-004",
                kpi_name="Confirmed Orders",
                domain="Commercial Sales",
                value=confirmed_orders,
                formatted_value=f"{confirmed_orders:,}",
                unit="Orders",
                trend="neutral",
            ),
            KPICard(
                kpi_id="KPI-005",
                kpi_name="AR Outstanding",
                domain="Accounts Receivable",
                value=ar_outstanding,
                formatted_value=f"₱{ar_outstanding:,.2f}",
                unit="PHP",
                trend="neutral",
            ),
            KPICard(
                kpi_id="KPI-007",
                kpi_name="Weighted Pipeline",
                domain="CRM Forecasting",
                value=weighted_pipeline,
                formatted_value=f"₱{weighted_pipeline:,.2f}",
                unit="PHP",
                trend="up" if weighted_pipeline > 0 else "neutral",
            ),
            KPICard(
                kpi_id="KPI-008",
                kpi_name="Win Rate",
                domain="Sales Performance",
                value=win_rate,
                formatted_value=f"{win_rate:.1f}%",
                unit="%",
                trend="up" if win_rate >= Decimal("30.0") else "neutral",
            ),
            KPICard(
                kpi_id="KPI-013",
                kpi_name="Inventory Value",
                domain="Inventory & Valuation",
                value=inventory_value,
                formatted_value=f"₱{inventory_value:,.2f}",
                unit="PHP",
                trend="neutral",
            ),
            KPICard(
                kpi_id="KPI-015",
                kpi_name="Low-Stock Items",
                domain="Inventory Stock Alert",
                value=low_stock_count,
                formatted_value=f"{low_stock_count:,}",
                unit="SKUs",
                trend="down" if low_stock_count > 0 else "neutral",
            ),
            KPICard(
                kpi_id="KPI-016",
                kpi_name="Purchase Spend",
                domain="Procurement",
                value=purchase_spend,
                formatted_value=f"₱{purchase_spend:,.2f}",
                unit="PHP",
                trend="neutral",
            ),
            KPICard(
                kpi_id="KPI-018",
                kpi_name="Days Sales Outstanding (DSO)",
                domain="Cash Flow & Credit",
                value=dso_days or Decimal("0.0"),
                formatted_value=f"{dso_days:.1f} days" if dso_days else "N/A",
                unit="Days",
                trend="neutral",
            ),
        ]

        return ExecutiveSummaryResponse(
            as_of_date=today,
            period_start=start,
            period_end=end,
            scorecards=scorecards,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Revenue & Gross Margin Report (KPI-001, KPI-002, KPI-003)
    # ──────────────────────────────────────────────────────────────────────────
    def get_revenue_report(
        self,
        context: ScopeContext,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> RevenueReportResponse:
        today = date.today()
        # Default: last 6 months
        end = period_end or today
        start = period_start or (end.replace(day=1) - timedelta(days=150)).replace(day=1)

        scoped_customer_ids = self._get_scoped_customer_ids(context)

        # Invoices query
        inv_q = select(
            Invoice.issue_date,
            Invoice.subtotal,
        ).where(
            Invoice.status.in_(["issued", "partially_paid", "paid"]),
            Invoice.issue_date >= start,
            Invoice.issue_date <= end,
        )
        if scoped_customer_ids is not None:
            inv_q = inv_q.where(Invoice.customer_id.in_(scoped_customer_ids))

        inv_rows = self.db.execute(inv_q).fetchall()

        # Credit notes query
        cn_q = select(
            CreditNote.issue_date,
            CreditNote.subtotal,
        ).where(
            CreditNote.status == "issued",
            CreditNote.issue_date >= start,
            CreditNote.issue_date <= end,
        )
        if scoped_customer_ids is not None:
            cn_q = cn_q.where(CreditNote.customer_id.in_(scoped_customer_ids))

        cn_rows = self.db.execute(cn_q).fetchall()

        # COGS query
        dt_start = datetime.combine(start, time.min, tzinfo=timezone.utc)
        dt_end = datetime.combine(end, time.max, tzinfo=timezone.utc)
        cogs_q = (
            select(
                Shipment.shipped_at,
                ShipmentItem.cogs_amount,
            )
            .join(Shipment, Shipment.id == ShipmentItem.shipment_id)
            .where(
                Shipment.status == "posted",
                Shipment.shipped_at >= dt_start,
                Shipment.shipped_at <= dt_end,
            )
        )
        cogs_rows = self.db.execute(cogs_q).fetchall()

        # Aggregate by YYYY-MM
        monthly_data: dict[str, dict[str, Any]] = {}

        for row in inv_rows:
            if not row.issue_date:
                continue
            month_key = row.issue_date.strftime("%Y-%m")
            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    "gross_invoiced": Decimal("0.00"),
                    "credit_notes": Decimal("0.00"),
                    "cogs": Decimal("0.00"),
                    "invoice_count": 0,
                }
            monthly_data[month_key]["gross_invoiced"] += Decimal(str(row.subtotal))
            monthly_data[month_key]["invoice_count"] += 1

        for row in cn_rows:
            if not row.issue_date:
                continue
            month_key = row.issue_date.strftime("%Y-%m")
            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    "gross_invoiced": Decimal("0.00"),
                    "credit_notes": Decimal("0.00"),
                    "cogs": Decimal("0.00"),
                    "invoice_count": 0,
                }
            monthly_data[month_key]["credit_notes"] += Decimal(str(row.subtotal))

        for row in cogs_rows:
            if not row.shipped_at:
                continue
            month_key = row.shipped_at.strftime("%Y-%m")
            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    "gross_invoiced": Decimal("0.00"),
                    "credit_notes": Decimal("0.00"),
                    "cogs": Decimal("0.00"),
                    "invoice_count": 0,
                }
            if row.cogs_amount:
                monthly_data[month_key]["cogs"] += Decimal(str(row.cogs_amount))

        # Build sorted list
        trend: list[RevenueMarginMonthlyPoint] = []
        tot_net_rev = Decimal("0.00")
        tot_cogs = Decimal("0.00")
        tot_invoices = 0
        tot_credit_notes = len(cn_rows)

        for month in sorted(monthly_data.keys()):
            d = monthly_data[month]
            gross = d["gross_invoiced"]
            credits = d["credit_notes"]
            net_rev = gross - credits
            month_cogs = d["cogs"]
            gm = net_rev - month_cogs
            gm_pct = (
                (gm / net_rev * Decimal("100")).quantize(Decimal("0.01"))
                if net_rev > Decimal("0.00")
                else Decimal("0.00")
            )

            tot_net_rev += net_rev
            tot_cogs += month_cogs
            tot_invoices += d["invoice_count"]

            trend.append(
                RevenueMarginMonthlyPoint(
                    month=month,
                    gross_invoiced=gross,
                    credit_notes=credits,
                    net_revenue=net_rev,
                    cogs=month_cogs,
                    gross_margin=gm,
                    gross_margin_pct=gm_pct,
                    invoice_count=d["invoice_count"],
                )
            )

        tot_gm = tot_net_rev - tot_cogs
        tot_gm_pct = (
            (tot_gm / tot_net_rev * Decimal("100")).quantize(Decimal("0.01"))
            if tot_net_rev > Decimal("0.00")
            else Decimal("0.00")
        )

        return RevenueReportResponse(
            period_start=start,
            period_end=end,
            net_revenue=tot_net_rev,
            gross_margin=tot_gm,
            gross_margin_pct=tot_gm_pct,
            total_invoices=tot_invoices,
            total_credit_notes=tot_credit_notes,
            trend=trend,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Accounts Receivable Aging Report (KPI-005, KPI-006, KPI-018)
    # ──────────────────────────────────────────────────────────────────────────
    def get_ar_aging_report(
        self,
        context: ScopeContext,
        as_of_date: date | None = None,
    ) -> ARAgingResponse:
        today = as_of_date or date.today()
        scoped_customer_ids = self._get_scoped_customer_ids(context)

        # Open invoices query
        q = (
            select(
                Invoice.id,
                Invoice.customer_id,
                Invoice.balance_due,
                Invoice.due_date,
                Customer.customer_no,
                Customer.name.label("customer_name"),
            )
            .join(Customer, Customer.id == Invoice.customer_id)
            .where(
                Invoice.status.in_(["issued", "partially_paid"]),
                Invoice.issue_date <= today,
                Invoice.balance_due > Decimal("0.00"),
            )
        )
        if scoped_customer_ids is not None:
            q = q.where(Invoice.customer_id.in_(scoped_customer_ids))

        rows = self.db.execute(q).fetchall()

        bucket_totals = {
            "current": {"label": "Current (Not Overdue)", "amount": Decimal("0.00"), "count": 0},
            "1-30": {"label": "1–30 Days Overdue", "amount": Decimal("0.00"), "count": 0},
            "31-60": {"label": "31–60 Days Overdue", "amount": Decimal("0.00"), "count": 0},
            "61-90": {"label": "61–90 Days Overdue", "amount": Decimal("0.00"), "count": 0},
            "90+": {"label": "90+ Days Overdue", "amount": Decimal("0.00"), "count": 0},
        }

        cust_matrix: dict[int, dict[str, Any]] = {}
        total_ar = Decimal("0.00")

        for row in rows:
            bal = Decimal(str(row.balance_due))
            total_ar += bal

            # Bucket classification
            if not row.due_date or row.due_date >= today:
                b_key = "current"
            else:
                overdue_days = (today - row.due_date).days
                if overdue_days <= 30:
                    b_key = "1-30"
                elif overdue_days <= 60:
                    b_key = "31-60"
                elif overdue_days <= 90:
                    b_key = "61-90"
                else:
                    b_key = "90+"

            bucket_totals[b_key]["amount"] += bal
            bucket_totals[b_key]["count"] += 1

            cid = row.customer_id
            if cid not in cust_matrix:
                cust_matrix[cid] = {
                    "customer_id": cid,
                    "customer_no": row.customer_no,
                    "customer_name": row.customer_name,
                    "total_balance": Decimal("0.00"),
                    "current": Decimal("0.00"),
                    "days_1_30": Decimal("0.00"),
                    "days_31_60": Decimal("0.00"),
                    "days_61_90": Decimal("0.00"),
                    "days_90_plus": Decimal("0.00"),
                }
            cust_matrix[cid]["total_balance"] += bal
            if b_key == "current":
                cust_matrix[cid]["current"] += bal
            elif b_key == "1-30":
                cust_matrix[cid]["days_1_30"] += bal
            elif b_key == "31-60":
                cust_matrix[cid]["days_31_60"] += bal
            elif b_key == "61-90":
                cust_matrix[cid]["days_61_90"] += bal
            else:
                cust_matrix[cid]["days_90_plus"] += bal

        buckets: list[ARAgingBucket] = []
        for k in ["current", "1-30", "31-60", "61-90", "90+"]:
            info = bucket_totals[k]
            amt = info["amount"]
            pct = (
                (amt / total_ar * Decimal("100")).quantize(Decimal("0.1"))
                if total_ar > Decimal("0.00")
                else Decimal("0.0")
            )
            buckets.append(
                ARAgingBucket(
                    bucket=k,
                    label=info["label"],
                    amount=amt,
                    count=info["count"],
                    percentage=pct,
                )
            )

        customer_rows = [
            ARAgingCustomerRow(**data)
            for data in sorted(
                cust_matrix.values(), key=lambda x: x["total_balance"], reverse=True
            )
        ]

        # DSO Calculation (KPI-018)
        t90_start = today - timedelta(days=90)
        t90_inv_q = select(func.coalesce(func.sum(Invoice.subtotal), Decimal("0.00"))).where(
            Invoice.status.in_(["issued", "partially_paid", "paid"]),
            Invoice.issue_date >= t90_start,
            Invoice.issue_date <= today,
        )
        if scoped_customer_ids is not None:
            t90_inv_q = t90_inv_q.where(Invoice.customer_id.in_(scoped_customer_ids))
        t90_revenue = Decimal(str(self.db.execute(t90_inv_q).scalar_one()))
        daily_rev = t90_revenue / Decimal("90") if t90_revenue > 0 else Decimal("0.00")
        dso_days = (
            (total_ar / daily_rev).quantize(Decimal("0.1"))
            if daily_rev > 0
            else None
        )

        return ARAgingResponse(
            as_of_date=today,
            total_outstanding=total_ar,
            buckets=buckets,
            customers=customer_rows,
            dso_days=dso_days,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Sales Pipeline & Velocity Report (KPI-007, KPI-008, KPI-009, KPI-010)
    # ──────────────────────────────────────────────────────────────────────────
    def get_pipeline_report(
        self,
        context: ScopeContext,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> PipelineReportResponse:
        today = date.today()
        start = period_start or today.replace(day=1)
        end = period_end or today
        dt_start = datetime.combine(start, time.min, tzinfo=timezone.utc)
        dt_end = datetime.combine(end, time.max, tzinfo=timezone.utc)

        # Open opportunities breakdown
        opp_q = select(
            Opportunity.stage,
            func.count(Opportunity.id).label("count"),
            func.coalesce(func.sum(Opportunity.estimated_amount), Decimal("0.00")).label("nominal"),
            func.coalesce(
                func.sum(Opportunity.estimated_amount * Opportunity.probability),
                Decimal("0.00"),
            ).label("weighted"),
        ).where(
            Opportunity.stage.notin_(["won", "lost"]),
        )
        opp_q = apply_scope(opp_q, Opportunity, context, self.db)
        opp_q = opp_q.group_by(Opportunity.stage)

        stage_rows = self.db.execute(opp_q).fetchall()
        stage_map = {row.stage: row for row in stage_rows}

        stage_order = [
            ("discovery", "Discovery"),
            ("proposal", "Proposal"),
            ("negotiation", "Negotiation"),
        ]
        stages: list[PipelineStageSummary] = []
        tot_open_count = 0
        tot_open_nominal = Decimal("0.00")
        tot_open_weighted = Decimal("0.00")

        for code, label in stage_order:
            if code in stage_map:
                r = stage_map[code]
                cnt = r.count
                nom = Decimal(str(r.nominal))
                wt = Decimal(str(r.weighted)).quantize(Decimal("0.01"))
            else:
                cnt = 0
                nom = Decimal("0.00")
                wt = Decimal("0.00")

            tot_open_count += cnt
            tot_open_nominal += nom
            tot_open_weighted += wt

            stages.append(
                PipelineStageSummary(
                    stage=code,
                    label=label,
                    count=cnt,
                    nominal_amount=nom,
                    weighted_amount=wt,
                )
            )

        # KPI-008: Win Rate
        closed_q = select(
            func.count(Opportunity.id),
            func.count(case((Opportunity.stage == "won", 1))),
        ).where(
            Opportunity.stage.in_(["won", "lost"]),
            Opportunity.closed_at >= dt_start,
            Opportunity.closed_at <= dt_end,
        )
        closed_q = apply_scope(closed_q, Opportunity, context, self.db)
        total_closed, total_won = self.db.execute(closed_q).fetchone() or (0, 0)
        win_rate = (
            Decimal(str((total_won / total_closed) * 100)).quantize(Decimal("0.01"))
            if total_closed > 0
            else Decimal("0.00")
        )

        # KPI-009: Lead Conversion Rate
        leads_q = select(
            func.count(Lead.id),
            func.count(case((Lead.status == "converted", 1))),
        ).where(
            Lead.created_at >= dt_start,
            Lead.created_at <= dt_end,
        )
        leads_q = apply_scope(leads_q, Lead, context, self.db)
        total_leads, converted_leads = self.db.execute(leads_q).fetchone() or (0, 0)
        lead_conv = (
            Decimal(str((converted_leads / total_leads) * 100)).quantize(Decimal("0.01"))
            if total_leads > 0
            else Decimal("0.00")
        )

        # KPI-010: Average Sales Cycle
        won_cycle_q = select(
            Opportunity.created_at,
            Opportunity.closed_at,
        ).where(
            Opportunity.stage == "won",
            Opportunity.closed_at >= dt_start,
            Opportunity.closed_at <= dt_end,
        )
        won_cycle_q = apply_scope(won_cycle_q, Opportunity, context, self.db)
        won_rows = self.db.execute(won_cycle_q).fetchall()
        if won_rows:
            days_sum = sum(
                (r.closed_at - r.created_at).total_seconds() / 86400.0
                for r in won_rows
                if r.closed_at and r.created_at
            )
            avg_cycle = Decimal(str(days_sum / len(won_rows))).quantize(Decimal("0.1"))
        else:
            avg_cycle = Decimal("0.0")

        return PipelineReportResponse(
            as_of_date=today,
            period_start=start,
            period_end=end,
            total_open_opportunities=tot_open_count,
            total_open_amount=tot_open_nominal,
            weighted_pipeline=tot_open_weighted,
            win_rate_pct=win_rate,
            lead_conversion_pct=lead_conv,
            avg_sales_cycle_days=avg_cycle,
            stages=stages,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Inventory Valuation & Low-Stock Alerts (KPI-013, KPI-015)
    # ──────────────────────────────────────────────────────────────────────────
    def get_inventory_report(
        self,
        context: ScopeContext,
        as_of_date: date | None = None,
    ) -> InventoryReportResponse:
        today = as_of_date or date.today()

        # Total valuation and warehouse summary (KPI-013)
        wh_q = (
            select(
                Warehouse.id,
                Warehouse.code,
                Warehouse.name,
                func.coalesce(
                    func.sum(InventoryBalance.qty_on_hand * InventoryBalance.avg_unit_cost),
                    Decimal("0.00"),
                ).label("total_val"),
                func.count(InventoryBalance.product_id).label("sku_cnt"),
            )
            .outerjoin(InventoryBalance, InventoryBalance.warehouse_id == Warehouse.id)
            .group_by(Warehouse.id, Warehouse.code, Warehouse.name)
            .order_by(Warehouse.code)
        )
        wh_rows = self.db.execute(wh_q).fetchall()

        total_value = Decimal("0.00")
        warehouses: list[WarehouseInventorySummary] = []
        for r in wh_rows:
            val = Decimal(str(r.total_val)).quantize(Decimal("0.01"))
            total_value += val
            warehouses.append(
                WarehouseInventorySummary(
                    warehouse_id=r.id,
                    warehouse_code=r.code,
                    warehouse_name=r.name,
                    total_value=val,
                    sku_count=r.sku_cnt,
                )
            )

        # Low-stock items list (KPI-015)
        low_q = (
            select(
                Product.id,
                Product.sku,
                Product.name,
                Product.uom,
                Product.reorder_point,
                func.coalesce(func.sum(InventoryBalance.qty_on_hand), Decimal("0.000")).label(
                    "on_hand"
                ),
                func.coalesce(func.sum(InventoryBalance.qty_reserved), Decimal("0.000")).label(
                    "reserved"
                ),
            )
            .outerjoin(InventoryBalance, InventoryBalance.product_id == Product.id)
            .where(
                Product.is_active == True,  # noqa: E712
                Product.product_type == "stock",
                Product.reorder_point > 0,
            )
            .group_by(Product.id, Product.sku, Product.name, Product.uom, Product.reorder_point)
            .having(
                func.coalesce(
                    func.sum(InventoryBalance.qty_on_hand - InventoryBalance.qty_reserved),
                    Decimal("0.000"),
                )
                < Product.reorder_point
            )
            .order_by(Product.sku)
        )
        low_rows = self.db.execute(low_q).fetchall()

        low_stock_items: list[LowStockItemRow] = []
        for r in low_rows:
            on_hand = Decimal(str(r.on_hand))
            reserved = Decimal(str(r.reserved))
            avail = on_hand - reserved
            reorder = Decimal(str(r.reorder_point))
            deficit = reorder - avail
            low_stock_items.append(
                LowStockItemRow(
                    product_id=r.id,
                    sku=r.sku,
                    name=r.name,
                    uom=r.uom,
                    qty_on_hand=on_hand,
                    qty_reserved=reserved,
                    qty_available=avail,
                    reorder_point=reorder,
                    deficit=deficit,
                )
            )

        return InventoryReportResponse(
            as_of_date=today,
            total_inventory_value=total_value,
            low_stock_count=len(low_stock_items),
            warehouses=warehouses,
            low_stock_items=low_stock_items,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Procurement & Vendor Spend Analytics (KPI-016, KPI-017)
    # ──────────────────────────────────────────────────────────────────────────
    def get_procurement_report(
        self,
        context: ScopeContext,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> ProcurementReportResponse:
        today = date.today()
        start = period_start or today.replace(day=1)
        end = period_end or today

        # Supplier bills query (KPI-016)
        spend_q = (
            select(
                Supplier.id,
                Supplier.supplier_no,
                Supplier.name.label("supplier_name"),
                func.coalesce(func.sum(SupplierInvoice.subtotal), Decimal("0.00")).label("spend"),
                func.count(SupplierInvoice.id).label("bill_count"),
            )
            .join(Supplier, Supplier.id == SupplierInvoice.supplier_id)
            .where(
                SupplierInvoice.status.in_(["approved", "partially_paid", "paid"]),
                SupplierInvoice.invoice_date >= start,
                SupplierInvoice.invoice_date <= end,
            )
            .group_by(Supplier.id, Supplier.supplier_no, Supplier.name)
            .order_by(func.sum(SupplierInvoice.subtotal).desc())
        )
        spend_rows = self.db.execute(spend_q).fetchall()

        tot_spend = Decimal("0.00")
        suppliers: list[SupplierSpendRow] = []
        for r in spend_rows:
            sp = Decimal(str(r.spend)).quantize(Decimal("0.01"))
            tot_spend += sp
            suppliers.append(
                SupplierSpendRow(
                    supplier_id=r.id,
                    supplier_no=r.supplier_no,
                    supplier_name=r.supplier_name,
                    spend=sp,
                    bill_count=r.bill_count,
                    on_time_rate_pct=None,
                )
            )

        # On-Time Delivery Rate (KPI-017)
        # Ratio of receipts delivered on or before purchase order expected_date
        ot_q = (
            select(
                func.count(GoodsReceipt.id),
                func.count(
                    case(
                        (
                            func.date(GoodsReceipt.received_at) <= PurchaseOrder.expected_date,
                            1,
                        )
                    )
                ),
            )
            .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id)
            .where(
                GoodsReceipt.status == "posted",
                PurchaseOrder.expected_date.is_not(None),
            )
        )
        total_receipts, on_time_receipts = self.db.execute(ot_q).fetchone() or (0, 0)
        overall_on_time = (
            Decimal(str((on_time_receipts / total_receipts) * 100)).quantize(Decimal("0.01"))
            if total_receipts > 0
            else Decimal("100.00")
        )

        return ProcurementReportResponse(
            period_start=start,
            period_end=end,
            total_purchase_spend=tot_spend,
            overall_on_time_rate_pct=overall_on_time,
            suppliers=suppliers,
        )
