"""
Unit Tests for Milestone V1.4: Analytical Data Model (Star Schema)
Roadmap §V1.4

Test Coverage:
1. Conformed Dimensions:
   - dim_date (2023-2026, calendar = fiscal, Manila timezone attributes, date_key YYYYMMDD, weekends)
   - dim_source_system (erp, legacy)
   - dim_customer (surrogate key customer_key, natural keys, SCD Type 2 tracking: valid_from, valid_to, is_current)
   - dim_product, dim_employee, dim_warehouse, dim_supplier (surrogate keys and business attributes)
2. Net Revenue Centavo Parity Contract:
   - Fact sales line net_revenue for ERP matches V0.9 operational report (ReportingService) to the centavo.
3. Fact Table Declared Grain & Uniqueness Enforcement:
   - fact_sales_line: (source_system_key, document_type, COALESCE(invoice_no, credit_note_no), line_number)
   - fact_opportunity_stage: (opportunity_id, transition_id)
   - fact_inventory_daily: (date_key, product_key, warehouse_key)
   - fact_purchase_line: (po_no, line_number)
   - fact_ar_allocation: (payment_no, allocation_id)
4. SCD Type 2 Discovery Lesson:
   - Demonstrates Type 1 flaw (history shifted to new region) vs Type 2 preservation (historical sales preserved in original region).
5. Mart CLI & Audit Logging:
   - CLI flags (--build, --scd-lesson, --check-grains) and audit tracking in etl.runs.
"""

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from analytics.db import init_analytics_db
from analytics.mart.builder import MartBuilder, date_to_key
from analytics.mart.cli import parse_args
from analytics.mart.scd_lesson import run_scd_discovery_lesson
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.authorization import ScopeContext
from app.modules.catalog.models import Product
from app.modules.crm.models import Customer
from app.modules.identity.models import User
from app.modules.organization.models import Department
from app.modules.reporting.service import ReportingService
from app.modules.sales.models import CreditNote, CreditNoteItem, Invoice, InvoiceItem, TaxRate


@pytest.fixture
def analytics_test_engine(db_session: Session) -> Engine:
    """Creates an isolated analytics engine for test execution."""
    erp_engine = db_session.get_bind()
    if erp_engine.dialect.name == "postgresql":
        analytics_url = os.getenv(
            "ANALYTICS_DATABASE_URL",
            "postgresql+psycopg://analytics_owner:analytics_owner_password@localhost:5432/erp_analytics",
        )
        try:
            engine = create_engine(analytics_url, pool_pre_ping=True)
            with engine.connect():
                pass
            init_analytics_db(engine)
            return engine
        except Exception:
            pass

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_analytics_db(engine)
    return engine


def test_date_to_key_conversion():
    """Verifies date_to_key produces integer YYYYMMDD format."""
    d = date(2025, 6, 15)
    assert date_to_key(d) == 20250615
    dt = datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)
    assert date_to_key(dt) == 20241231
    assert date_to_key(None) == 19000101


def test_conformed_dimensions(analytics_test_engine: Engine):
    """Test 1: Conformed dimensions populate surrogate keys and proper attributes."""
    builder = MartBuilder(engine=analytics_test_engine)

    # 1. Populate dim_date (2023-2026)
    count_dates = builder.populate_dim_date(
        start_date=date(2023, 1, 1), end_date=date(2026, 12, 31)
    )
    assert count_dates == 1461  # 365 * 3 + 366 (leap year 2024)

    is_pg = analytics_test_engine.dialect.name == "postgresql"
    qual_date = "mart.dim_date" if is_pg else "dim_date"

    with analytics_test_engine.connect() as conn:
        date_sample = (
            conn.execute(text(f"SELECT * FROM {qual_date} WHERE date_key = 20240229"))
            .mappings()
            .one()
        )
        assert date_sample["year"] == 2024
        assert date_sample["month"] == 2
        assert date_sample["day"] == 29
        assert date_sample["fiscal_year"] == 2024  # Calendar = Fiscal
        assert date_sample["month_name"] == "February"

        # Check weekend flag (2024-03-02 is Saturday)
        sat = conn.execute(
            text(f"SELECT is_weekend FROM {qual_date} WHERE date_key = 20240302")
        ).scalar()
        assert bool(sat) is True

        # 2024-03-04 is Monday
        mon = conn.execute(
            text(f"SELECT is_weekend FROM {qual_date} WHERE date_key = 20240304")
        ).scalar()
        assert bool(mon) is False

    # 2. Populate dim_source_system
    count_sys = builder.populate_dim_source_system()
    assert count_sys == 2
    qual_sys = "mart.dim_source_system" if is_pg else "dim_source_system"
    with analytics_test_engine.connect() as conn:
        sys_codes = [r[0] for r in conn.execute(text(f"SELECT code FROM {qual_sys}")).fetchall()]
        assert "erp" in sys_codes
        assert "legacy" in sys_codes

    # 3. Populate dim_warehouse & dim_supplier & dim_employee
    count_wh = builder.build_dim_warehouse()
    assert count_wh >= 1

    count_sup = builder.build_dim_supplier()
    assert count_sup >= 1

    count_emp = builder.build_dim_employee()
    assert count_emp >= 1


def test_customer_scd_type2_dimension(analytics_test_engine: Engine):
    """Test 2: dim_customer manages surrogate keys, effective dates, and SCD Type 2 tracking."""
    builder = MartBuilder(engine=analytics_test_engine)
    is_pg = analytics_test_engine.dialect.name == "postgresql"
    qual_cust = "mart.dim_customer" if is_pg else "dim_customer"

    # Seed an ERP staging customer
    stg_cust = "staging.stg_customers" if is_pg else "stg_customers"
    with analytics_test_engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {stg_cust} (
                    id INTEGER PRIMARY KEY,
                    customer_no TEXT,
                    name TEXT,
                    customer_type TEXT,
                    industry TEXT,
                    credit_limit NUMERIC,
                    payment_terms_days INTEGER,
                    status TEXT,
                    created_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(text(f"DELETE FROM {stg_cust} WHERE id = 101;"))
        conn.execute(
            text(
                f"""
                INSERT INTO {stg_cust} (id, customer_no, name, customer_type, industry, credit_limit, payment_terms_days, status, created_at)
                VALUES (101, 'CUS-101', 'Philippine Industrial Corp', 'company', 'Manufacturing', 750000.0, 30, 'active', :ca)
                """
            ),
            {"ca": datetime(2024, 1, 15, tzinfo=UTC)},
        )

    # Build dim_customer
    count_cust = builder.build_dim_customer(scd_type=2)
    assert count_cust >= 1

    with analytics_test_engine.connect() as conn:
        cust = (
            conn.execute(text(f"SELECT * FROM {qual_cust} WHERE customer_id = 101"))
            .mappings()
            .one()
        )
        assert cust["customer_key"] is not None
        assert cust["customer_no"] == "CUS-101"
        assert cust["name"] == "Philippine Industrial Corp"
        assert bool(cust["is_current"]) is True
        assert cust["valid_from"] is not None
        assert cust["valid_to"] is None


def test_net_revenue_centavo_parity_contract(db_session: Session, analytics_test_engine: Engine):
    """
    Test 3: Net Revenue Centavo Parity Contract (Roadmap §V1.4 Exit Criteria)
    Mart net revenue for ERP sales lines equals the V0.9 operational report to the centavo.
    """
    # 1. Seed Tax, Department, Customer, Product
    tax = db_session.query(TaxRate).filter_by(code="VAT12").first()
    if not tax:
        tax = TaxRate(code="VAT12", name="Value Added Tax", rate=Decimal("0.1200"))
        db_session.add(tax)
        db_session.flush()

    dept = db_session.query(Department).filter_by(code="SALES").first()
    if not dept:
        dept = Department(code="SALES", name="Sales Operations")
        db_session.add(dept)
        db_session.flush()

    customer = db_session.query(Customer).filter_by(customer_no="CUS-PARITY-001").first()
    if not customer:
        customer = Customer(
            customer_no="CUS-PARITY-001",
            name="Centavo Parity Enterprises",
            customer_type="company",
            payment_terms_days=30,
            credit_limit=Decimal("500000.00"),
        )
        db_session.add(customer)
        db_session.flush()

    product = db_session.query(Product).filter_by(sku="SKU-PARITY-001").first()
    if not product:
        product = Product(
            sku="SKU-PARITY-001",
            name="Precision Steel Component",
            list_price=Decimal("250.75"),
            uom="pc",
            product_type="stock",
            tax_rate_id=tax.id,
        )
        db_session.add(product)
        db_session.flush()

    # 2. Seed Invoices in May 2025:
    # Inv 1: subtotal 12,537.50
    # Inv 2: subtotal 8,024.00
    # Credit Note 1: subtotal 2,507.50
    # Operational Net Revenue = 12,537.50 + 8,024.00 - 2,507.50 = 18,054.00
    test_month_start = date(2025, 5, 1)
    test_month_end = date(2025, 5, 31)

    inv1 = Invoice(
        invoice_no="INV-PARITY-001",
        customer_id=customer.id,
        status="issued",
        issue_date=date(2025, 5, 10),
        due_date=date(2025, 6, 10),
        currency_code="PHP",
        subtotal=Decimal("12537.50"),
        discount_total=Decimal("0.00"),
        tax_total=Decimal("1504.50"),
        grand_total=Decimal("14042.00"),
        amount_paid=Decimal("0.00"),
        amount_credited=Decimal("0.00"),
        balance_due=Decimal("14042.00"),
    )
    inv1_item = InvoiceItem(
        invoice=inv1,
        line_no=1,
        product_id=product.id,
        description="Precision Steel Component",
        uom="pc",
        quantity=Decimal("50.000"),
        unit_price=Decimal("250.7500"),
        discount_amount=Decimal("0.00"),
        tax_rate_id=tax.id,
        tax_rate=Decimal("0.1200"),
        line_net=Decimal("12537.50"),
        line_tax=Decimal("1504.50"),
        line_total=Decimal("14042.00"),
    )

    inv2 = Invoice(
        invoice_no="INV-PARITY-002",
        customer_id=customer.id,
        status="paid",
        issue_date=date(2025, 5, 18),
        due_date=date(2025, 6, 18),
        currency_code="PHP",
        subtotal=Decimal("8024.00"),
        discount_total=Decimal("0.00"),
        tax_total=Decimal("962.88"),
        grand_total=Decimal("8986.88"),
        amount_paid=Decimal("8986.88"),
        amount_credited=Decimal("0.00"),
        balance_due=Decimal("0.00"),
    )
    inv2_item = InvoiceItem(
        invoice=inv2,
        line_no=1,
        product_id=product.id,
        description="Precision Steel Component",
        uom="pc",
        quantity=Decimal("32.000"),
        unit_price=Decimal("250.7500"),
        discount_amount=Decimal("0.00"),
        tax_rate_id=tax.id,
        tax_rate=Decimal("0.1200"),
        line_net=Decimal("8024.00"),
        line_tax=Decimal("962.88"),
        line_total=Decimal("8986.88"),
    )

    db_session.add_all([inv1, inv1_item, inv2, inv2_item])
    db_session.flush()

    cn1 = CreditNote(
        credit_note_no="CN-PARITY-001",
        invoice_id=inv1.id,
        customer_id=customer.id,
        status="issued",
        issue_date=date(2025, 5, 25),
        reason="damaged",
        currency_code="PHP",
        subtotal=Decimal("2507.50"),
        tax_total=Decimal("300.90"),
        grand_total=Decimal("2808.40"),
    )
    cn1_item = CreditNoteItem(
        credit_note=cn1,
        line_no=1,
        product_id=product.id,
        description="Precision Steel Component (Damaged)",
        uom="pc",
        quantity=Decimal("10.000"),
        unit_price=Decimal("250.7500"),
        discount_amount=Decimal("0.00"),
        tax_rate_id=tax.id,
        tax_rate=Decimal("0.1200"),
        line_net=Decimal("2507.50"),
        line_tax=Decimal("300.90"),
        line_total=Decimal("2808.40"),
    )
    db_session.add_all([cn1, cn1_item])
    db_session.commit()

    # 3. Calculate V0.9 Operational Net Revenue via ReportingService query contract
    admin_user = User(
        id=999,
        email="admin@parity.ph",
        full_name="Admin Parity Test",
        password_hash="hash",
        is_active=True,
        is_superuser=True,
    )
    context = ScopeContext(user=admin_user, scope="all")
    rep_svc = ReportingService(db_session)
    op_report = rep_svc.get_executive_summary(
        context=context, period_start=test_month_start, period_end=test_month_end
    )
    net_kpi = next(s for s in op_report.scorecards if s.kpi_id == "KPI-001")
    v09_net_revenue = Decimal(str(net_kpi.value))

    # 4. Populate analytics staging tables to mirror extraction
    is_pg = analytics_test_engine.dialect.name == "postgresql"
    stg_inv = "staging.stg_invoices" if is_pg else "stg_invoices"
    stg_inv_lines = "staging.stg_invoice_lines" if is_pg else "stg_invoice_lines"
    raw_cn = "raw.credit_notes" if is_pg else "credit_notes"
    raw_cn_items = "raw.credit_note_items" if is_pg else "credit_note_items"
    stg_cust = "staging.stg_customers" if is_pg else "stg_customers"
    stg_prod = "staging.stg_products" if is_pg else "stg_products"

    with analytics_test_engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {stg_inv} (
                    id INTEGER PRIMARY KEY,
                    invoice_no TEXT,
                    customer_id INTEGER,
                    issue_date TIMESTAMP,
                    status TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {stg_inv_lines} (
                    id INTEGER PRIMARY KEY,
                    invoice_id INTEGER,
                    product_id INTEGER,
                    quantity NUMERIC,
                    unit_price NUMERIC,
                    discount_amount NUMERIC,
                    line_subtotal NUMERIC,
                    line_tax NUMERIC
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {raw_cn} (
                    id INTEGER PRIMARY KEY,
                    credit_note_no TEXT,
                    customer_id INTEGER,
                    issue_date TIMESTAMP,
                    status TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {raw_cn_items} (
                    id INTEGER PRIMARY KEY,
                    credit_note_id INTEGER,
                    product_id INTEGER,
                    quantity NUMERIC,
                    unit_price NUMERIC,
                    subtotal NUMERIC
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {stg_cust} (
                    id INTEGER PRIMARY KEY,
                    customer_no TEXT,
                    name TEXT,
                    customer_type TEXT,
                    industry TEXT,
                    credit_limit NUMERIC,
                    payment_terms_days INTEGER,
                    status TEXT,
                    created_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {stg_prod} (
                    id INTEGER PRIMARY KEY,
                    sku TEXT,
                    name TEXT,
                    category TEXT,
                    uom TEXT,
                    standard_cost NUMERIC,
                    list_price NUMERIC,
                    status TEXT
                )
                """
            )
        )

        # Clear and insert test records
        conn.execute(text(f"DELETE FROM {stg_inv} WHERE invoice_no LIKE 'INV-PARITY-%';"))
        conn.execute(text(f"DELETE FROM {stg_inv_lines};"))
        conn.execute(text(f"DELETE FROM {raw_cn} WHERE credit_note_no = 'CN-PARITY-001';"))
        conn.execute(text(f"DELETE FROM {raw_cn_items};"))
        conn.execute(text(f"DELETE FROM {stg_cust} WHERE id = :cid;"), {"cid": customer.id})
        conn.execute(text(f"DELETE FROM {stg_prod} WHERE id = :pid;"), {"pid": product.id})

        conn.execute(
            text(
                f"""
                INSERT INTO {stg_cust} (id, customer_no, name, customer_type, industry, credit_limit, payment_terms_days, status, created_at)
                VALUES (:cid, 'CUS-PARITY-001', 'Centavo Parity Enterprises', 'company', 'Manufacturing', 500000.0, 30, 'active', :ca)
                """
            ),
            {"cid": customer.id, "ca": datetime(2025, 1, 1, tzinfo=UTC)},
        )

        conn.execute(
            text(
                f"""
                INSERT INTO {stg_prod} (id, sku, name, category, uom, standard_cost, list_price, status)
                VALUES (:pid, 'SKU-PARITY-001', 'Precision Steel Component', 'Components', 'pc', 120.00, 250.75, 'active')
                """
            ),
            {"pid": product.id},
        )

        # Invoices
        conn.execute(
            text(
                f"""
                INSERT INTO {stg_inv} (id, invoice_no, customer_id, issue_date, status)
                VALUES (1, 'INV-PARITY-001', :cid, :d1, 'issued'),
                       (2, 'INV-PARITY-002', :cid, :d2, 'paid')
                """
            ),
            {
                "cid": customer.id,
                "d1": datetime(2025, 5, 10, tzinfo=UTC),
                "d2": datetime(2025, 5, 18, tzinfo=UTC),
            },
        )
        conn.execute(
            text(
                f"""
                INSERT INTO {stg_inv_lines} (id, invoice_id, product_id, quantity, unit_price, discount_amount, line_subtotal, line_tax)
                VALUES (101, 1, :pid, 50.0, 250.75, 0.0, 12537.50, 1504.50),
                       (102, 2, :pid, 32.0, 250.75, 0.0, 8024.00, 962.88)
                """
            ),
            {"pid": product.id},
        )

        # Credit Note
        conn.execute(
            text(
                f"""
                INSERT INTO {raw_cn} (id, credit_note_no, customer_id, issue_date, status)
                VALUES (1, 'CN-PARITY-001', :cid, :d3, 'issued')
                """
            ),
            {"cid": customer.id, "d3": datetime(2025, 5, 25, tzinfo=UTC)},
        )
        conn.execute(
            text(
                f"""
                INSERT INTO {raw_cn_items} (id, credit_note_id, product_id, quantity, unit_price, subtotal)
                VALUES (201, 1, :pid, 10.0, 250.75, 2507.50)
                """
            ),
            {"pid": product.id},
        )

    # 5. Build Mart (Dimensions & Facts)
    builder = MartBuilder(engine=analytics_test_engine)
    builder.populate_dim_date(date(2025, 1, 1), date(2025, 12, 31))
    builder.populate_dim_source_system()
    builder.build_dim_customer()
    builder.build_dim_product()
    builder.build_dim_employee()
    builder.build_fact_sales_line()

    # 6. Aggregate Net Revenue in Mart for May 2025 (ERP only)
    qual_fact = "mart.fact_sales_line" if is_pg else "fact_sales_line"
    with analytics_test_engine.connect() as conn:
        mart_net_revenue = conn.execute(
            text(
                f"""
                SELECT SUM(net_revenue)
                FROM {qual_fact}
                WHERE source_system = 'erp'
                  AND date_key BETWEEN 20250501 AND 20250531
                """
            )
        ).scalar()

    mart_net_decimal = Decimal(str(mart_net_revenue)).quantize(Decimal("0.01"))
    v09_net_decimal = v09_net_revenue.quantize(Decimal("0.01"))

    # Assert exact centavo parity (diff == 0.00)
    parity_diff = abs(mart_net_decimal - v09_net_decimal)
    assert parity_diff == Decimal("0.00"), (
        f"Centavo mismatch! Mart: {mart_net_decimal}, V0.9: {v09_net_decimal}"
    )
    assert mart_net_decimal == Decimal("18054.00")


def test_fact_table_grain_uniqueness(analytics_test_engine: Engine):
    """
    Test 4: Declared Grain Enforcement & Uniqueness Verification (Roadmap §V1.4 Exit Criteria)
    Every fact table's grain is enforced and verified with 0 duplicate grain rows.
    """
    builder = MartBuilder(engine=analytics_test_engine)
    summary = builder.build_all()

    assert summary["status"] == "success"
    grains = summary["grain_verification"]

    # Verify all 5 fact tables passed grain checks
    assert "fact_sales_line" in grains
    assert grains["fact_sales_line"]["passed"] is True
    assert (
        grains["fact_sales_line"]["grain"]
        == "(source_system_key, document_type, invoice_no/credit_note_no, line_number)"
    )

    assert "fact_opportunity_stage" in grains
    assert grains["fact_opportunity_stage"]["passed"] is True
    assert grains["fact_opportunity_stage"]["grain"] == "(opportunity_id, transition_id)"

    assert "fact_inventory_daily" in grains
    assert grains["fact_inventory_daily"]["passed"] is True
    assert grains["fact_inventory_daily"]["grain"] == "(date_key, product_key, warehouse_key)"

    assert "fact_purchase_line" in grains
    assert grains["fact_purchase_line"]["passed"] is True
    assert grains["fact_purchase_line"]["grain"] == "(po_no, line_number)"

    assert "fact_ar_allocation" in grains
    assert grains["fact_ar_allocation"]["passed"] is True
    assert grains["fact_ar_allocation"]["grain"] == "(payment_no, allocation_id)"

    # Direct verify_grain_uniqueness call returns passed=True across all facts
    verification_results = builder.verify_grain_uniqueness()
    for fact_name, v_res in verification_results.items():
        assert v_res["passed"] is True, f"Fact table {fact_name} failed grain uniqueness!"


def test_scd_type2_discovery_lesson(analytics_test_engine: Engine):
    """
    Test 5: SCD Type 2 Discovery Lesson (Roadmap §V1.4 Exit Criteria)
    Demonstrates that Type 1 shifts historical 2024 sales into the new region,
    while Type 2 preserves historical sales in the original region.
    """
    builder = MartBuilder(engine=analytics_test_engine)
    builder.populate_dim_date(date(2023, 1, 1), date(2026, 12, 31))
    builder.populate_dim_source_system()

    lesson_results = run_scd_discovery_lesson(engine=analytics_test_engine)

    assert lesson_results["customer_name"] == "Atlas Discovery Corp"
    assert lesson_results["original_region"] == "Luzon"
    assert lesson_results["updated_region"] == "Visayas"

    # Baseline 2024: 100,000 PHP in Luzon
    assert lesson_results["sales_2024_baseline"].get("Luzon") == 100000.0

    # Type 1 Flaw: 2024 sales retroactively shifted to Visayas!
    assert lesson_results["sales_2024_after_type1"].get("Visayas") == 100000.0
    assert lesson_results["sales_2024_after_type1"].get("Luzon") is None

    # Type 2 Historical Preservation: 2024 sales preserved in Luzon!
    assert lesson_results["sales_2024_under_type2"].get("Luzon") == 100000.0
    assert lesson_results["sales_2024_under_type2"].get("Visayas") is None

    # Type 2 Current Activity: 2025 sales properly recorded in Visayas!
    assert lesson_results["sales_2025_under_type2"].get("Visayas") == 50000.0


def test_mart_cli_and_audit_logging(analytics_test_engine: Engine):
    """Test 6: CLI Argument Parsing and Audit Run Logging in etl.runs."""
    # 1. CLI Parsing
    args_build = parse_args(["--job-name", "nightly_mart_sync"])
    assert args_build.job_name == "nightly_mart_sync"
    assert args_build.build is True

    args_lesson = parse_args(["--scd-lesson"])
    assert args_lesson.scd_lesson is True

    args_grain = parse_args(["--check-grains"])
    assert args_grain.check_grains is True

    # 2. MartBuilder logs run in etl.runs
    builder = MartBuilder(engine=analytics_test_engine)
    summary = builder.build_all(job_name="test_mart_job")

    assert summary["status"] == "success"
    run_id = summary["run_id"]
    assert run_id > 0

    is_pg = analytics_test_engine.dialect.name == "postgresql"
    qual_runs = "etl.runs" if is_pg else "runs"

    with analytics_test_engine.connect() as conn:
        run_record = (
            conn.execute(text(f"SELECT * FROM {qual_runs} WHERE run_id = :rid"), {"rid": run_id})
            .mappings()
            .one()
        )
        assert run_record["job"] == "test_mart_job"
        assert run_record["status"] == "success"
        assert run_record["finished_at"] is not None
