"""
Unit Tests for Milestone V1.2: Transformation Pipeline (Roadmap §V1.2)
Covers:
1. Idempotency: Multiple transformation runs produce identical row counts and SHA-256 checksums.
2. Deduplication: Append-only raw revisions are deduplicated via ROW_NUMBER() window function.
3. Derived Metrics: Calculation of line_subtotal, line_margin, etc.
4. Legacy Parsing: Parse attempts for dates/currencies/terms with parse_error capture and 0 rows dropped.
5. Failure Cascading: Upstream failure halts and skips all transitive downstream dependents.
6. Data Freshness: etl.model_runs records MAX(_extracted_at) source freshness.
7. DAG & CLI: Dependency graph resolution, cycle detection, and CLI parsing.
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest
from analytics.db import init_analytics_db
from analytics.extract.extractor import Extractor, get_session
from analytics.extract.models import EtlModelRun
from analytics.transform.cli import parse_args
from analytics.transform.dag import CyclicDependencyError, ModelDAG
from analytics.transform.runner import TransformRunner
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.modules.catalog.models import Product
from app.modules.crm.models import Customer
from app.modules.organization.models import Department
from app.modules.sales.models import TaxRate


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


@pytest.fixture
def seed_erp_data(db_session: Session):
    """Seeds baseline ERP entities for extraction and transformation tests."""
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

    customer = db_session.query(Customer).filter_by(customer_no="CUS-EXTRACT-001").first()
    if not customer:
        customer = Customer(
            customer_no="CUS-EXTRACT-001",
            name="Apex Industrial Supplies",
            customer_type="company",
            payment_terms_days=30,
            credit_limit=Decimal("500000.00"),
        )
        db_session.add(customer)
        db_session.flush()

    product = db_session.query(Product).filter_by(sku="SKU-EXTRACT-001").first()
    if not product:
        product = Product(
            sku="SKU-EXTRACT-001",
            name="Steel Pipe 10mm",
            list_price=Decimal("1500.00"),
            uom="pc",
            product_type="stock",
            tax_rate_id=tax.id,
        )
        db_session.add(product)
        db_session.flush()

    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(product)
    return {
        "dept": dept,
        "tax": tax,
        "customer": customer,
        "product": product,
    }


def test_staging_idempotency_and_checksum_consistency(
    db_session: Session, analytics_test_engine: Engine, seed_erp_data
):
    """Test 1: Running the transformation pipeline repeatedly produces identical rows and checksums."""
    erp_engine = db_session.get_bind()
    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=0,
    )
    extract_summary = extractor.run(job_name="test_extract_for_transform")
    assert extract_summary["status"] == "success"

    runner = TransformRunner(engine=analytics_test_engine)

    # First run on core entities + legacy
    models_to_test = [
        "stg_customers",
        "stg_products",
        "stg_departments",
        "stg_tax_rates",
        "stg_legacy_customers",
        "stg_legacy_sales",
    ]
    run1 = runner.run(models=models_to_test, job_name="transform_run_1")
    assert run1["status"] == "success"
    assert len(run1["models"]) == len(models_to_test)

    run1_checksums = {m["model"]: m["checksum"] for m in run1["models"]}
    run1_rows = {m["model"]: m["rows"] for m in run1["models"]}

    # Second run on the exact same raw data
    run2 = runner.run(models=models_to_test, job_name="transform_run_2")
    assert run2["status"] == "success"

    run2_checksums = {m["model"]: m["checksum"] for m in run2["models"]}
    run2_rows = {m["model"]: m["rows"] for m in run2["models"]}

    # Prove Idempotency
    for m in models_to_test:
        assert run1_rows[m] == run2_rows[m], f"Row count mismatch on model {m}"
        assert run1_checksums[m] == run2_checksums[m], f"Checksum mismatch on model {m}"


def test_deduplication_via_window_function(analytics_test_engine: Engine):
    """Test 2: Append-only raw revisions are deduplicated into the latest record in staging."""
    is_postgres = analytics_test_engine.dialect.name == "postgresql"
    target_raw = "raw.customers" if is_postgres else "customers"
    target_stg = "staging.stg_customers" if is_postgres else "stg_customers"
    cascade = " CASCADE" if is_postgres else ""

    try:
        with analytics_test_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {target_raw}{cascade};"))
            conn.execute(
                text(
                    f"""
                CREATE TABLE IF NOT EXISTS {target_raw} (
                    _raw_id INTEGER PRIMARY KEY,
                    id INTEGER,
                    customer_no TEXT,
                    name TEXT,
                    customer_type TEXT,
                    status TEXT,
                    tin TEXT,
                    email TEXT,
                    phone TEXT,
                    website TEXT,
                    industry TEXT,
                    payment_terms_days INTEGER,
                    credit_limit NUMERIC,
                    owner_user_id INTEGER,
                    notes TEXT,
                    version INTEGER,
                    created_at TIMESTAMP,
                    created_by TEXT,
                    updated_at TIMESTAMP,
                    updated_by TEXT,
                    _extracted_at TIMESTAMP,
                    _run_id INTEGER,
                    _source TEXT
                );
                """
                )
            )
            # Older version of Customer 99
            conn.execute(
                text(
                    f"""
                INSERT INTO {target_raw} (_raw_id, id, customer_no, name, customer_type, status, payment_terms_days, credit_limit, version, _extracted_at, _run_id, _source)
                VALUES (1, 99, 'CUS-099', 'Old Name Corp', 'company', 'active', 15, 100000.00, 1, '2026-10-10 10:00:00', 1, 'erp');
                """
                )
            )
            # Newer updated version of Customer 99
            conn.execute(
                text(
                    f"""
                INSERT INTO {target_raw} (_raw_id, id, customer_no, name, customer_type, status, payment_terms_days, credit_limit, version, _extracted_at, _run_id, _source)
                VALUES (2, 99, 'CUS-099', 'New Updated Name Corp', 'company', 'active', 30, 250000.00, 2, '2026-10-11 12:00:00', 2, 'erp');
                """
                )
            )

        runner = TransformRunner(engine=analytics_test_engine)
        summary = runner.run(models=["stg_customers"])
        assert summary["status"] == "success"

        with analytics_test_engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT id, name, credit_limit, payment_terms_days, version FROM {target_stg} WHERE id = 99"
                )
            ).fetchall()
            assert len(rows) == 1
            cust_id, name, credit_limit, terms, ver = rows[0]
            assert cust_id == 99
            assert name == "New Updated Name Corp"
            assert Decimal(str(credit_limit)) == Decimal("250000.00")
            assert terms == 30
            assert ver == 2
    finally:
        with analytics_test_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {target_raw}{cascade};"))
            conn.execute(text(f"DROP TABLE IF EXISTS {target_stg}{cascade};"))


def test_derived_metrics_on_sales_order_lines(analytics_test_engine: Engine):
    """Test 3: Staging derived fields line_subtotal and line_margin are correctly calculated."""
    is_postgres = analytics_test_engine.dialect.name == "postgresql"
    target_raw = "raw.sales_order_items" if is_postgres else "sales_order_items"
    target_stg = "staging.stg_sales_order_lines" if is_postgres else "stg_sales_order_lines"
    cascade = " CASCADE" if is_postgres else ""

    try:
        with analytics_test_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {target_raw}{cascade};"))
            conn.execute(
                text(
                    f"""
                CREATE TABLE IF NOT EXISTS {target_raw} (
                    _raw_id INTEGER PRIMARY KEY,
                    id INTEGER,
                    sales_order_id INTEGER,
                    line_no INTEGER,
                    product_id INTEGER,
                    description TEXT,
                    uom TEXT,
                    quantity NUMERIC,
                    unit_price NUMERIC,
                    discount_amount NUMERIC,
                    tax_rate_id INTEGER,
                    tax_rate NUMERIC,
                    line_net NUMERIC,
                    line_tax NUMERIC,
                    line_total NUMERIC,
                    quantity_invoiced NUMERIC,
                    quantity_shipped NUMERIC,
                    _extracted_at TIMESTAMP,
                    _run_id INTEGER,
                    _source TEXT
                );
                """
                )
            )
            conn.execute(
                text(
                    f"""
                INSERT INTO {target_raw} (
                    _raw_id, id, sales_order_id, line_no, product_id, description, uom,
                    quantity, unit_price, discount_amount, tax_rate_id, tax_rate,
                    line_net, line_tax, line_total, quantity_invoiced, quantity_shipped,
                    _extracted_at, _run_id, _source
                ) VALUES (
                    1, 101, 50, 1, 10, 'Industrial Motor', 'pc',
                    4.0, 2500.0, 500.0, 1, 0.12,
                    9500.0, 1140.0, 10640.0, 0, 0,
                    '2026-10-11 12:00:00', 1, 'erp'
                );
                """
                )
            )

        runner = TransformRunner(engine=analytics_test_engine)
        summary = runner.run(models=["stg_sales_order_lines"])
        assert summary["status"] == "success"

        with analytics_test_engine.connect() as conn:
            row = conn.execute(
                text(
                    f"SELECT line_subtotal, line_margin, line_total FROM {target_stg} WHERE id = 101"
                )
            ).fetchone()
            assert row is not None
            # line_subtotal = (4 * 2500) - 500 = 9500.00
            assert Decimal(str(row[0])) == Decimal("9500.00")
            assert Decimal(str(row[1])) == Decimal("9500.00")
            assert Decimal(str(row[2])) == Decimal("10640.00")
    finally:
        with analytics_test_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {target_raw}{cascade};"))
            conn.execute(text(f"DROP TABLE IF EXISTS {target_stg}{cascade};"))


def test_legacy_data_parse_attempts_and_error_preservation(
    db_session: Session, analytics_test_engine: Engine
):
    """Test 4: Legacy CSV parse attempts extract clean dates/currencies while preserving raw dirty strings."""
    erp_engine = db_session.get_bind()
    is_postgres = analytics_test_engine.dialect.name == "postgresql"
    target_raw_cust = "raw.legacy_customers" if is_postgres else "legacy_customers"
    target_raw_sales = "raw.legacy_sales" if is_postgres else "legacy_sales"
    cascade = " CASCADE" if is_postgres else ""

    with analytics_test_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {target_raw_cust}{cascade};"))
        conn.execute(text(f"DROP TABLE IF EXISTS {target_raw_sales}{cascade};"))

    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=0,
    )
    summary = extractor.run(legacy_only=True)
    assert summary["status"] == "success"

    runner = TransformRunner(engine=analytics_test_engine)
    trans_summary = runner.run(models=["stg_legacy_customers", "stg_legacy_sales"])
    assert trans_summary["status"] == "success"

    # 1. Verify stg_legacy_customers
    target_cust = "staging.stg_legacy_customers" if is_postgres else "stg_legacy_customers"
    with analytics_test_engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {target_cust}")).scalar_one()
        assert count == 250, "All 250 legacy customer rows must be retained without drop"

        # Check a row with currency symbol '₱'
        sample = conn.execute(
            text(
                f"SELECT credit_limit, parsed_credit_limit, credit_terms, parsed_credit_terms_days, parsed_tax_id FROM {target_cust} WHERE legacy_customer_id = 'LEG-CUS-0002'"
            )
        ).fetchone()
        assert "₱" in sample[0]
        assert Decimal(str(sample[1])) == Decimal("190000.00")
        assert sample[2] == "0 days"
        assert sample[3] == 0
        assert "-" not in sample[4]

    # 2. Verify stg_legacy_sales
    target_sales = "staging.stg_legacy_sales" if is_postgres else "stg_legacy_sales"
    with analytics_test_engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {target_sales}")).scalar_one()
        assert count == 1500, "All 1500 legacy sales rows must be retained without drop"

        # Check an invalid date row (e.g. 2024-02-30)
        invalid_date_row = conn.execute(
            text(
                f"SELECT order_date, parsed_order_date, parse_error FROM {target_sales} WHERE order_date = '2024-02-30' LIMIT 1"
            )
        ).fetchone()
        assert invalid_date_row is not None
        assert invalid_date_row[0] == "2024-02-30"
        assert invalid_date_row[1] is None, "Invalid date must have NULL parsed_order_date"
        assert "invalid_order_date" in invalid_date_row[2]

        # Check a valid slash-formatted date row (e.g. 08/29/2023)
        slash_row = conn.execute(
            text(
                f"SELECT order_date, parsed_order_date, parse_error FROM {target_sales} WHERE order_date = '08/29/2023' LIMIT 1"
            )
        ).fetchone()
        assert slash_row is not None
        assert slash_row[0] == "08/29/2023"
        assert slash_row[1] == "2023-08-29", "Slash date MM/DD/YYYY must normalize to YYYY-MM-DD"


def test_failure_cascading_halts_downstream_dependents(
    tmp_path: Path, analytics_test_engine: Engine
):
    """Test 5: If an upstream model fails, downstream dependents are cascaded to 'skipped'."""
    # Create mock models directory with a failure cascade
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    # Upstream model with deliberate syntax error
    (models_dir / "stg_bad_upstream.sql").write_text(
        """-- Model: stg_bad_upstream
-- Target: staging.stg_bad_upstream
-- Depends on: []
SELECT * FROM non_existent_table_that_throws_error;
""",
        encoding="utf-8",
    )

    # Downstream model depending on the bad upstream model
    (models_dir / "stg_child_downstream.sql").write_text(
        """-- Model: stg_child_downstream
-- Target: staging.stg_child_downstream
-- Depends on: [stg_bad_upstream]
SELECT * FROM {{ staging }}.stg_bad_upstream;
""",
        encoding="utf-8",
    )

    # Independent valid model
    (models_dir / "stg_independent.sql").write_text(
        """-- Model: stg_independent
-- Target: staging.stg_independent
-- Depends on: []
SELECT 1 AS num_col;
""",
        encoding="utf-8",
    )

    runner = TransformRunner(engine=analytics_test_engine, models_dir=models_dir)
    summary = runner.run()

    assert summary["status"] == "failed"
    model_status_map = {m["model"]: m["status"] for m in summary["models"]}
    assert model_status_map["stg_bad_upstream"] == "failed"
    assert model_status_map["stg_child_downstream"] == "skipped"
    assert model_status_map["stg_independent"] == "success"

    # Verify audit records in etl.model_runs
    session = get_session(analytics_test_engine)
    records = (
        session.execute(select(EtlModelRun).where(EtlModelRun.run_id == summary["run_id"]))
        .scalars()
        .all()
    )
    rec_status_map = {r.model_name: r.status for r in records}
    assert rec_status_map["stg_bad_upstream"] == "failed"
    assert rec_status_map["stg_child_downstream"] == "skipped"
    assert rec_status_map["stg_independent"] == "success"


def test_data_freshness_tracking(db_session: Session, analytics_test_engine: Engine, seed_erp_data):
    """Test 6: etl.model_runs records MAX(_extracted_at) source data freshness."""
    erp_engine = db_session.get_bind()
    is_postgres = analytics_test_engine.dialect.name == "postgresql"
    target_raw = "raw.customers" if is_postgres else "customers"
    cascade = " CASCADE" if is_postgres else ""

    with analytics_test_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {target_raw}{cascade};"))

    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=0,
    )
    extract_summary = extractor.run(
        tables=["customers"], full_refresh=True, job_name="test_freshness"
    )
    assert extract_summary["status"] == "success"

    runner = TransformRunner(engine=analytics_test_engine)
    transform_summary = runner.run(models=["stg_customers"])
    assert transform_summary["status"] == "success"

    session = get_session(analytics_test_engine)
    model_run = session.execute(
        select(EtlModelRun).where(
            EtlModelRun.run_id == transform_summary["run_id"],
            EtlModelRun.model_name == "stg_customers",
        )
    ).scalar_one()

    assert model_run.data_freshness is not None
    assert model_run.status == "success"
    assert model_run.rows_affected >= 1
    assert model_run.checksum is not None
    assert len(model_run.checksum) == 64  # SHA-256


def test_cli_parsing_and_cycle_detection(tmp_path: Path):
    """Test 7: CLI argument parsing and DAG cyclic dependency detection."""
    args = parse_args(["--model", "stg_customers", "--job-name", "custom_job"])
    assert args.models == ["stg_customers"]
    assert args.job_name == "custom_job"
    assert not args.dry_run

    dry_args = parse_args(["--dry-run"])
    assert dry_args.dry_run

    # Cycle detection test
    cycle_dir = tmp_path / "cyclic_models"
    cycle_dir.mkdir()
    (cycle_dir / "model_a.sql").write_text(
        "-- Model: model_a\n-- Depends on: [model_b]\nSELECT 1;", encoding="utf-8"
    )
    (cycle_dir / "model_b.sql").write_text(
        "-- Model: model_b\n-- Depends on: [model_a]\nSELECT 1;", encoding="utf-8"
    )

    dag = ModelDAG(models_dir=cycle_dir)
    with pytest.raises(CyclicDependencyError, match="Cyclic dependency detected"):
        dag.get_execution_order()
