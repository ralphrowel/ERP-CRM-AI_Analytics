"""
Unit and integration tests for Milestone V0.9: Operational Reporting, KPI Dictionary, and Analytical Query Patterns.
Validates:
1. Executive Scorecard metrics (KPI-001 through KPI-018).
2. Net Revenue and Gross Margin trend calculations with Credit Notes & COGS.
3. Accounts Receivable (AR) Aging 5-bucket distribution and customer matrix.
4. CRM Pipeline funnel, Win Rate, Lead Conversion, and Sales Cycle velocity.
5. Inventory valuation and Low-Stock deficit alerts.
6. Procurement spend aggregation and Supplier On-Time Delivery rate.
7. RBAC scoping enforcement ('own' vs 'all' customer scoping).
8. HTTP REST API endpoints under /api/v1/reporting/...
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.authorization import ScopeContext
from app.core.database import get_db
from app.core.numbering import DocumentSequence
from app.core.security import hash_password
from app.main import app
from app.modules.catalog.models import Product, ProductCategory
from app.modules.crm.models import Customer, Lead, Opportunity
from app.modules.identity.models import Permission, Role, RolePermission, User, UserRole
from app.modules.identity.service import IdentityService
from app.modules.inventory.models import (
    InventoryBalance,
    Shipment,
    ShipmentItem,
    Warehouse,
)
from app.modules.purchasing.models import (
    GoodsReceipt,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierInvoice,
)
from app.modules.reporting.service import ReportingService
from app.modules.sales.models import (
    CreditNote,
    Invoice,
    SalesOrder,
    SalesOrderItem,
    TaxRate,
)


@pytest.fixture
def reporting_data(db_session: Session):
    """Seed comprehensive fixture data across all operational domains."""
    # 1. Document sequences
    sequences = [
        ("customer", "CUS", False),
        ("sales_order", "SO", True),
        ("invoice", "INV", True),
        ("credit_note", "CN", True),
    ]
    for doc_type, prefix, inc_yr in sequences:
        if not db_session.query(DocumentSequence).filter_by(doc_type=doc_type).first():
            db_session.add(
                DocumentSequence(
                    doc_type=doc_type,
                    prefix=prefix,
                    include_year=inc_yr,
                    padding=6,
                    next_value=1,
                )
            )

    # 2. Roles & Permissions
    # Ensure reporting permissions exist
    perm_codes = [
        "report:read",
        "report:sales",
        "report:financial",
        "report:inventory",
        "report:purchasing",
    ]
    perm_objs = {}
    for code in perm_codes:
        p = db_session.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code, description=f"Test perm {code}", module="reporting")
            db_session.add(p)
            db_session.flush()
        perm_objs[code] = p

    # Roles
    admin_role = db_session.query(Role).filter_by(code="admin").first()
    if not admin_role:
        admin_role = Role(code="admin", name="Admin", is_system=True)
        db_session.add(admin_role)
        db_session.flush()

    sales_rep_role = db_session.query(Role).filter_by(code="sales_rep").first()
    if not sales_rep_role:
        sales_rep_role = Role(code="sales_rep", name="Sales Rep", is_system=True)
        db_session.add(sales_rep_role)
        db_session.flush()

    # Role Permissions
    for p in perm_objs.values():
        if not db_session.query(RolePermission).filter_by(role_id=admin_role.id, permission_id=p.id).first():
            db_session.add(RolePermission(role_id=admin_role.id, permission_id=p.id, scope="all"))

    # Sales rep gets report:read (own) and report:sales (own)
    for p_code in ["report:read", "report:sales"]:
        p = perm_objs[p_code]
        if not db_session.query(RolePermission).filter_by(role_id=sales_rep_role.id, permission_id=p.id).first():
            db_session.add(RolePermission(role_id=sales_rep_role.id, permission_id=p.id, scope="own"))

    # Users
    admin_user = User(
        email="admin_rep@corp.local",
        password_hash=hash_password("AdminPass123!"),
        full_name="Admin Reporter",
        is_superuser=True,
        is_active=True,
    )
    rep_user = User(
        email="rep_test@corp.local",
        password_hash=hash_password("RepPass123!"),
        full_name="Rep User",
        is_superuser=False,
        is_active=True,
    )
    other_user = User(
        email="other_rep@corp.local",
        password_hash=hash_password("OtherPass123!"),
        full_name="Other Rep",
        is_superuser=False,
        is_active=True,
    )
    db_session.add_all([admin_user, rep_user, other_user])
    db_session.flush()

    db_session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
    db_session.add(UserRole(user_id=rep_user.id, role_id=sales_rep_role.id))
    db_session.flush()

    # 3. Tax Rate
    tax = db_session.query(TaxRate).filter_by(code="VAT12").first()
    if not tax:
        tax = TaxRate(code="VAT12", name="VAT 12%", rate=Decimal("0.1200"), is_default=True, is_active=True)
        db_session.add(tax)
        db_session.flush()

    # 4. Customers
    cust1 = Customer(
        customer_no="CUS-000001",
        name="Alpha Mega Corp",
        status="active",
        owner_user_id=rep_user.id,
    )
    cust2 = Customer(
        customer_no="CUS-000002",
        name="Beta Logistics",
        status="active",
        owner_user_id=other_user.id,
    )
    db_session.add_all([cust1, cust2])
    db_session.flush()

    # 5. Warehouses & Products
    wh1 = Warehouse(code="WH-MAIN", name="Central Manila Warehouse", is_active=True, is_default=True)
    wh2 = Warehouse(code="WH-CEBU", name="Cebu Regional Hub", is_active=True, is_default=False)
    db_session.add_all([wh1, wh2])
    db_session.flush()

    cat = ProductCategory(name="Electronics", is_active=True)
    db_session.add(cat)
    db_session.flush()

    prod1 = Product(
        sku="SKU-ROUTER-01",
        name="Gigabit Enterprise Router",
        category_id=cat.id,
        product_type="stock",
        uom="pc",
        list_price=Decimal("15000.00"),
        reorder_point=Decimal("20.000"),
        tax_rate_id=tax.id,
        is_active=True,
    )
    prod2 = Product(
        sku="SKU-CABLE-100",
        name="Cat6 Ethernet Cable Reel 100m",
        category_id=cat.id,
        product_type="stock",
        uom="box",
        list_price=Decimal("2500.00"),
        reorder_point=Decimal("10.000"),
        tax_rate_id=tax.id,
        is_active=True,
    )
    db_session.add_all([prod1, prod2])
    db_session.flush()

    # Inventory balances:
    # prod1: 5 on hand (reorder 20 -> low stock alert deficit = 15)
    # prod2: 50 on hand (reorder 10 -> sufficient)
    b1 = InventoryBalance(
        product_id=prod1.id,
        warehouse_id=wh1.id,
        qty_on_hand=Decimal("5.000"),
        qty_reserved=Decimal("0.000"),
        avg_unit_cost=Decimal("9500.0000"),
    )
    b2 = InventoryBalance(
        product_id=prod2.id,
        warehouse_id=wh1.id,
        qty_on_hand=Decimal("30.000"),
        qty_reserved=Decimal("5.000"),
        avg_unit_cost=Decimal("1400.0000"),
    )
    b3 = InventoryBalance(
        product_id=prod2.id,
        warehouse_id=wh2.id,
        qty_on_hand=Decimal("20.000"),
        qty_reserved=Decimal("0.000"),
        avg_unit_cost=Decimal("1400.0000"),
    )
    db_session.add_all([b1, b2, b3])
    db_session.flush()

    today = date.today()

    # 6. Sales Orders, Shipments & Invoices
    # SO1 (cust1)
    so1 = SalesOrder(
        order_no="SO-2026-000001",
        customer_id=cust1.id,
        warehouse_id=wh1.id,
        status="confirmed",
        order_date=today,
        subtotal=Decimal("45000.00"),
        tax_total=Decimal("5400.00"),
        grand_total=Decimal("50400.00"),
    )
    db_session.add(so1)
    db_session.flush()

    so_item = SalesOrderItem(
        sales_order_id=so1.id,
        line_no=1,
        product_id=prod1.id,
        description="Router",
        uom="pc",
        quantity=Decimal("3.000"),
        unit_price=Decimal("15000.0000"),
        tax_rate_id=tax.id,
        tax_rate=tax.rate,
        line_net=Decimal("45000.00"),
        line_tax=Decimal("5400.00"),
        line_total=Decimal("50400.00"),
    )
    db_session.add(so_item)
    db_session.flush()

    # Shipment with COGS
    shipment = Shipment(
        shipment_no="SHP-2026-000001",
        sales_order_id=so1.id,
        warehouse_id=wh1.id,
        status="posted",
        shipped_at=datetime.now(UTC),
    )
    db_session.add(shipment)
    db_session.flush()

    shp_item = ShipmentItem(
        shipment_id=shipment.id,
        sales_order_item_id=so_item.id,
        product_id=prod1.id,
        quantity=Decimal("3.000"),
        unit_cost=Decimal("9500.0000"),
        cogs_amount=Decimal("28500.00"),
    )
    db_session.add(shp_item)
    db_session.flush()

    # Invoices:
    # Inv 1 (cust1): Subtotal 100,000, Tax 12,000, Grand 112,000, Paid 12,000, Balance 100,000, due today (Current)
    inv1 = Invoice(
        invoice_no="INV-2026-000001",
        customer_id=cust1.id,
        sales_order_id=so1.id,
        status="partially_paid",
        issue_date=today,
        due_date=today,
        subtotal=Decimal("100000.00"),
        tax_total=Decimal("12000.00"),
        grand_total=Decimal("112000.00"),
        amount_paid=Decimal("12000.00"),
        balance_due=Decimal("100000.00"),
    )
    # Inv 2 (cust1): Subtotal 50,000, Tax 6,000, Grand 56,000, Balance 56,000, due 20 days ago (1-30 bucket)
    inv2 = Invoice(
        invoice_no="INV-2026-000002",
        customer_id=cust1.id,
        status="issued",
        issue_date=today - timedelta(days=25),
        due_date=today - timedelta(days=20),
        subtotal=Decimal("50000.00"),
        tax_total=Decimal("6000.00"),
        grand_total=Decimal("56000.00"),
        balance_due=Decimal("56000.00"),
    )
    # Inv 3 (cust2): Subtotal 80,000, Tax 9,600, Grand 89,600, Balance 89,600, due 45 days ago (31-60 bucket)
    inv3 = Invoice(
        invoice_no="INV-2026-000003",
        customer_id=cust2.id,
        status="issued",
        issue_date=today - timedelta(days=50),
        due_date=today - timedelta(days=45),
        subtotal=Decimal("80000.00"),
        tax_total=Decimal("9600.00"),
        grand_total=Decimal("89600.00"),
        balance_due=Decimal("89600.00"),
    )
    db_session.add_all([inv1, inv2, inv3])
    db_session.flush()

    # Credit Note against Inv 1: Subtotal 10,000
    cn1 = CreditNote(
        credit_note_no="CN-2026-000001",
        invoice_id=inv1.id,
        customer_id=cust1.id,
        status="issued",
        issue_date=today,
        reason="discount",
        subtotal=Decimal("10000.00"),
        tax_total=Decimal("1200.00"),
        grand_total=Decimal("11200.00"),
    )
    db_session.add(cn1)
    db_session.flush()

    # 7. CRM: Opportunities & Leads
    # Opp 1: Discovery, 50,000 * 0.20 = 10,000 weighted
    opp1 = Opportunity(
        opportunity_no="OPP-000001",
        name="Alpha Fiber Upgrade",
        customer_id=cust1.id,
        stage="discovery",
        estimated_amount=Decimal("50000.00"),
        probability=Decimal("0.2000"),
        owner_user_id=rep_user.id,
    )
    # Opp 2: Proposal, 100,000 * 0.50 = 50,000 weighted
    opp2 = Opportunity(
        opportunity_no="OPP-000002",
        name="Beta Fleet Telecom",
        customer_id=cust2.id,
        stage="proposal",
        estimated_amount=Decimal("100000.00"),
        probability=Decimal("0.5000"),
        owner_user_id=other_user.id,
    )
    # Opp 3: Closed Won (2 days duration)
    opp3 = Opportunity(
        opportunity_no="OPP-000003",
        name="Completed Project",
        customer_id=cust1.id,
        stage="won",
        estimated_amount=Decimal("60000.00"),
        probability=Decimal("1.0000"),
        closed_at=datetime.now(UTC),
        created_at=datetime.now(UTC) - timedelta(days=5),
        owner_user_id=rep_user.id,
    )
    # Opp 4: Closed Lost
    opp4 = Opportunity(
        opportunity_no="OPP-000004",
        name="Lost Proposal",
        customer_id=cust2.id,
        stage="lost",
        lost_reason="competitor",
        estimated_amount=Decimal("40000.00"),
        probability=Decimal("0.0000"),
        closed_at=datetime.now(UTC),
        owner_user_id=other_user.id,
    )
    db_session.add_all([opp1, opp2, opp3, opp4])

    # Leads: 2 total, 1 converted
    lead1 = Lead(
        lead_no="LEAD-000001",
        first_name="Juan",
        last_name="Dela Cruz",
        status="converted",
        email="juan@lead.local",
        converted_at=datetime.now(UTC),
        converted_customer_id=cust1.id,
        owner_user_id=rep_user.id,
    )
    lead2 = Lead(
        lead_no="LEAD-000002",
        first_name="Maria",
        last_name="Santos",
        status="new",
        email="maria@lead.local",
        owner_user_id=rep_user.id,
    )
    db_session.add_all([lead1, lead2])
    db_session.flush()

    # 8. Purchasing: Supplier, PO, Supplier Invoice
    supp1 = Supplier(
        supplier_no="SUP-000001",
        name="TechSource Pacific",
        is_active=True,
    )
    db_session.add(supp1)
    db_session.flush()

    po1 = PurchaseOrder(
        po_no="PO-2026-000001",
        supplier_id=supp1.id,
        warehouse_id=wh1.id,
        status="received",
        order_date=today - timedelta(days=10),
        expected_date=today - timedelta(days=3),
        subtotal=Decimal("40000.00"),
        grand_total=Decimal("44800.00"),
    )
    db_session.add(po1)
    db_session.flush()

    gr1 = GoodsReceipt(
        gr_no="GR-2026-000001",
        purchase_order_id=po1.id,
        warehouse_id=wh1.id,
        status="posted",
        received_at=datetime.now(UTC) - timedelta(days=4),  # received before expected_date -> on-time
    )
    db_session.add(gr1)
    db_session.flush()

    supp_inv1 = SupplierInvoice(
        bill_no="BILL-2026-000001",
        supplier_id=supp1.id,
        purchase_order_id=po1.id,
        supplier_invoice_ref="INV-SUP-9912",
        status="approved",
        invoice_date=today - timedelta(days=5),
        due_date=today + timedelta(days=25),
        subtotal=Decimal("40000.00"),
        grand_total=Decimal("44800.00"),
        balance_due=Decimal("44800.00"),
    )
    db_session.add(supp_inv1)
    db_session.commit()

    return {
        "admin_user": admin_user,
        "rep_user": rep_user,
        "other_user": other_user,
        "cust1": cust1,
        "cust2": cust2,
        "prod1": prod1,
        "prod2": prod2,
        "wh1": wh1,
        "wh2": wh2,
    }


def test_reporting_executive_summary_scorecards(db_session: Session, reporting_data: dict):
    """
    Validates Executive Summary Scorecards (KPI-001 through KPI-018) for Admin (scope: all).
    """
    service = ReportingService(db_session)
    admin_ctx = ScopeContext(user=reporting_data["admin_user"], scope="all")

    today = date.today()
    summary = service.get_executive_summary(
        context=admin_ctx,
        period_start=today - timedelta(days=60),
    )

    # Convert scorecards to map
    cards = {c.kpi_id: c for c in summary.scorecards}

    # Total Invoices: inv1 (100k) + inv2 (50k) + inv3 (80k) = 230,000 subtotal
    # Credit Notes: cn1 (10,000)
    # KPI-001 Net Revenue = 230,000 - 10,000 = 220,000.00
    assert cards["KPI-001"].value == Decimal("220000.00")

    # KPI-002 Gross Margin: Net Rev (220,000) - COGS (28,500) = 191,500.00
    assert cards["KPI-002"].value == Decimal("191500.00")

    # KPI-003 Gross Margin %: 191,500 / 220,000 * 100 = 87.05%
    assert cards["KPI-003"].value == Decimal("87.05")

    # KPI-004 Confirmed Orders: so1 (status confirmed) = 1
    assert cards["KPI-004"].value == 1

    # KPI-005 AR Outstanding: inv1 (100k) + inv2 (56k) + inv3 (89.6k) = 245,600.00
    assert cards["KPI-005"].value == Decimal("245600.00")

    # KPI-007 Weighted Pipeline: opp1 (50k * 0.2 = 10k) + opp2 (100k * 0.5 = 50k) = 60,000.00
    assert cards["KPI-007"].value == Decimal("60000.00")

    # KPI-008 Win Rate: opp3 (won) / (opp3 + opp4 (lost)) = 1 / 2 = 50.00%
    assert cards["KPI-008"].value == Decimal("50.00")

    # KPI-013 Inventory Value:
    # prod1: 5 * 9500 = 47,500
    # prod2 wh1: 30 * 1400 = 42,000
    # prod2 wh2: 20 * 1400 = 28,000
    # Total = 117,500.00
    assert cards["KPI-013"].value == Decimal("117500.00")

    # KPI-015 Low Stock Items: prod1 has 5 on hand vs 20 reorder point -> 1 item
    assert cards["KPI-015"].value == 1

    # KPI-016 Purchase Spend: supp_inv1 = 40,000.00
    assert cards["KPI-016"].value == Decimal("40000.00")


def test_ar_aging_buckets_and_customer_matrix(db_session: Session, reporting_data: dict):
    """
    Validates AR Aging 5-bucket distribution and customer matrix (KPI-005, KPI-006).
    """
    service = ReportingService(db_session)
    admin_ctx = ScopeContext(user=reporting_data["admin_user"], scope="all")

    ar_report = service.get_ar_aging_report(context=admin_ctx)

    assert ar_report.total_outstanding == Decimal("245600.00")

    bucket_map = {b.bucket: b for b in ar_report.buckets}
    # Current: inv1 (due today) = 100,000
    assert bucket_map["current"].amount == Decimal("100000.00")
    # 1-30 days overdue: inv2 (due 20 days ago) = 56,000
    assert bucket_map["1-30"].amount == Decimal("56000.00")
    # 31-60 days overdue: inv3 (due 45 days ago) = 89,600
    assert bucket_map["31-60"].amount == Decimal("89600.00")
    # 61-90 and 90+: 0
    assert bucket_map["61-90"].amount == Decimal("0.00")
    assert bucket_map["90+"].amount == Decimal("0.00")

    # Customers breakdown
    assert len(ar_report.customers) == 2
    c_map = {c.customer_no: c for c in ar_report.customers}
    assert c_map["CUS-000001"].total_balance == Decimal("156000.00")
    assert c_map["CUS-000001"].current == Decimal("100000.00")
    assert c_map["CUS-000001"].days_1_30 == Decimal("56000.00")
    assert c_map["CUS-000002"].total_balance == Decimal("89600.00")
    assert c_map["CUS-000002"].days_31_60 == Decimal("89600.00")


def test_sales_pipeline_velocity_report(db_session: Session, reporting_data: dict):
    """
    Validates CRM Pipeline stages, Win Rate, and Lead Conversion (KPI-007, KPI-008, KPI-009, KPI-010).
    """
    service = ReportingService(db_session)
    admin_ctx = ScopeContext(user=reporting_data["admin_user"], scope="all")

    report = service.get_pipeline_report(context=admin_ctx)

    assert report.total_open_opportunities == 2
    assert report.total_open_amount == Decimal("150000.00")
    assert report.weighted_pipeline == Decimal("60000.00")
    assert report.win_rate_pct == Decimal("50.00")
    # 2 leads total, 1 converted -> 50%
    assert report.lead_conversion_pct == Decimal("50.00")
    assert report.avg_sales_cycle_days > Decimal("0.0")

    stage_map = {s.stage: s for s in report.stages}
    assert stage_map["discovery"].count == 1
    assert stage_map["discovery"].nominal_amount == Decimal("50000.00")
    assert stage_map["proposal"].count == 1
    assert stage_map["proposal"].nominal_amount == Decimal("100000.00")


def test_inventory_valuation_and_low_stock_report(db_session: Session, reporting_data: dict):
    """
    Validates Inventory valuation and low stock alert (KPI-013, KPI-015).
    """
    service = ReportingService(db_session)
    admin_ctx = ScopeContext(user=reporting_data["admin_user"], scope="all")

    inv_report = service.get_inventory_report(context=admin_ctx)

    assert inv_report.total_inventory_value == Decimal("117500.00")
    assert inv_report.low_stock_count == 1

    low_item = inv_report.low_stock_items[0]
    assert low_item.sku == "SKU-ROUTER-01"
    assert low_item.qty_on_hand == Decimal("5.000")
    assert low_item.reorder_point == Decimal("20.000")
    assert low_item.deficit == Decimal("15.000")

    wh_map = {w.warehouse_code: w for w in inv_report.warehouses}
    assert wh_map["WH-MAIN"].total_value == Decimal("89500.00")  # 47,500 + 42,000
    assert wh_map["WH-CEBU"].total_value == Decimal("28000.00")  # 28,000


def test_procurement_report(db_session: Session, reporting_data: dict):
    """
    Validates Procurement spend and on-time receipt rate (KPI-016, KPI-017).
    """
    service = ReportingService(db_session)
    admin_ctx = ScopeContext(user=reporting_data["admin_user"], scope="all")

    proc_report = service.get_procurement_report(context=admin_ctx)

    assert proc_report.total_purchase_spend == Decimal("40000.00")
    assert proc_report.overall_on_time_rate_pct == Decimal("100.00")
    assert len(proc_report.suppliers) == 1
    assert proc_report.suppliers[0].supplier_no == "SUP-000001"
    assert proc_report.suppliers[0].spend == Decimal("40000.00")


def test_rbac_scoping_rep_vs_admin(db_session: Session, reporting_data: dict):
    """
    Validates RBAC Object-Level Scoping:
    Sales Rep (scope: own) only sees their own assigned customer data (cust1),
    excluding cust2.
    """
    service = ReportingService(db_session)
    rep_user = reporting_data["rep_user"]
    rep_ctx = ScopeContext(user=rep_user, scope="own")

    today = date.today()
    rep_summary = service.get_executive_summary(
        context=rep_ctx,
        period_start=today - timedelta(days=60),
    )
    cards = {c.kpi_id: c for c in rep_summary.scorecards}

    # cust1 invoices: inv1 (100k) + inv2 (50k) = 150k
    # credit note: cn1 (10k)
    # Net Rev = 140,000.00 (cust2's 80k is excluded!)
    assert cards["KPI-001"].value == Decimal("140000.00")

    # AR Outstanding for cust1: inv1 (100k) + inv2 (56k) = 156,000.00 (cust2's 89.6k excluded!)
    assert cards["KPI-005"].value == Decimal("156000.00")

    # Weighted Pipeline: only opp1 (10k) owned by rep (opp2 owned by other_user excluded!)
    assert cards["KPI-007"].value == Decimal("10000.00")


def test_reporting_api_endpoints_via_http(db_session: Session, reporting_data: dict):
    """
    Validates HTTP REST endpoints under /api/v1/reporting/... with authentication token.
    """
    identity_svc = IdentityService(db_session)
    _, token, _ = identity_svc.authenticate_user("admin_rep@corp.local", "AdminPass123!")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Summary
        res = client.get("/api/v1/reporting/summary", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "scorecards" in data
        assert len(data["scorecards"]) > 0

        # 2. Revenue Trend
        res = client.get("/api/v1/reporting/revenue", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "trend" in data

        # 3. AR Aging
        res = client.get("/api/v1/reporting/ar-aging", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "buckets" in data
        assert "customers" in data

        # 4. Pipeline
        res = client.get("/api/v1/reporting/pipeline", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "stages" in data

        # 5. Inventory
        res = client.get("/api/v1/reporting/inventory", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "warehouses" in data
        assert "low_stock_items" in data

        # 6. Procurement
        res = client.get("/api/v1/reporting/procurement", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "suppliers" in data
    finally:
        app.dependency_overrides.clear()
