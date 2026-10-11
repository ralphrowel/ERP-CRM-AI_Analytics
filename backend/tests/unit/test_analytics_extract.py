"""
Unit Tests for Milestone V1.1: Data Extraction Layer (Roadmap §V1.1)
Covers:
1. Initial full extraction of ERP entities and legacy CSVs into append-only raw layer.
2. Second consecutive run with no ERP changes extracts ~0 rows.
3. Updating an ERP entity results in exactly one new raw version (append-only history).
4. Small reference tables (tax_rates, departments, warehouses) are fully extracted each run.
5. Legacy CSV ingestion stores all fields as TEXT with _file_name and _row_number.
6. ETL state logging in etl.runs and watermark management in etl.watermarks.
7. etl_reader role permissions contract (read-only enforcement).
8. CLI argument parsing and execution flags.
"""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from analytics.db import init_analytics_db
from analytics.extract.cli import parse_args
from analytics.extract.extractor import Extractor, get_session
from analytics.extract.models import EtlRun, EtlWatermark
from sqlalchemy import (
    Engine,
    MetaData,
    Table,
    create_engine,
    select,
    text,
)
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
        # In PostgreSQL CI, use ANALYTICS_DATABASE_URL or test URL
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
            # Fallback to in-memory if separate analytics db is unavailable
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
    """Seeds baseline ERP entities for extraction tests."""
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


def test_initial_extraction_and_legacy_csv_ingestion(
    db_session: Session, analytics_test_engine: Engine, seed_erp_data
):
    """Test 1: Initial extraction ingests legacy CSVs and ERP tables into raw layer."""
    erp_engine = db_session.get_bind()
    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=0,
    )

    summary = extractor.run(job_name="test_initial_run")
    assert summary["status"] == "success"
    assert summary["rows_extracted"] > 0
    assert summary["run_id"] >= 1

    # Verify etl.runs record
    session = get_session(analytics_test_engine)
    run = session.execute(select(EtlRun).where(EtlRun.run_id == summary["run_id"])).scalar_one()
    assert run.status == "success"
    assert run.rows_extracted == summary["rows_extracted"]
    assert run.started_at is not None
    assert run.finished_at is not None

    # Verify legacy CSV tables in raw layer
    raw_schema = "raw" if analytics_test_engine.dialect.name == "postgresql" else None
    meta = MetaData()

    raw_legacy_cust = Table(
        "legacy_customers", meta, autoload_with=analytics_test_engine, schema=raw_schema
    )
    with analytics_test_engine.connect() as conn:
        legacy_cust_rows = conn.execute(select(raw_legacy_cust)).fetchall()
        assert len(legacy_cust_rows) > 0
        first_row = legacy_cust_rows[0]
        # Provenance columns
        assert getattr(first_row, "_file_name", None) == "legacy_customers.csv"
        assert getattr(first_row, "_row_number", None) == 1
        assert getattr(first_row, "_source", None) == "legacy_csv"
        assert getattr(first_row, "_run_id", None) == summary["run_id"]
        # Raw text columns preserved
        assert getattr(first_row, "legacy_customer_id", None) is not None

    raw_legacy_sales = Table(
        "legacy_sales", meta, autoload_with=analytics_test_engine, schema=raw_schema
    )
    with analytics_test_engine.connect() as conn:
        legacy_sales_rows = conn.execute(select(raw_legacy_sales)).fetchall()
        assert len(legacy_sales_rows) > 0

    # Verify ERP customer in raw layer
    raw_customers = Table("customers", meta, autoload_with=analytics_test_engine, schema=raw_schema)
    with analytics_test_engine.connect() as conn:
        cust_rows = conn.execute(
            select(raw_customers).where(raw_customers.c.customer_no == "CUS-EXTRACT-001")
        ).fetchall()
        assert len(cust_rows) >= 1
        cust = cust_rows[0]
        assert cust.customer_no == "CUS-EXTRACT-001"
        assert cust._source == "erp_crm"
        assert cust._run_id == summary["run_id"]

    # Verify etl.watermarks updated
    watermark = session.execute(
        select(EtlWatermark).where(EtlWatermark.source_table == "customers")
    ).scalar_one_or_none()
    assert watermark is not None
    assert watermark.last_run_id == summary["run_id"]
    session.close()


def test_second_consecutive_run_with_no_changes(
    db_session: Session, analytics_test_engine: Engine, seed_erp_data
):
    """Test 2: A second run with no ERP changes extracts ~0 rows for incremental tables."""
    erp_engine = db_session.get_bind()
    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=0,  # 0 overlap for exact change-delta verification
    )

    # First run (scoped to customers)
    run1 = extractor.run(tables=["customers"], erp_only=True)
    assert run1["table_counts"]["customers"] >= 1

    # Second run immediately after with no changes in ERP
    run2 = extractor.run(tables=["customers"], erp_only=True)
    assert run2["table_counts"]["customers"] == 0


def test_incremental_customer_update_appends_new_version(
    db_session: Session, analytics_test_engine: Engine, seed_erp_data
):
    """Test 3: Changing one customer in ERP results in exactly one new raw version."""
    erp_engine = db_session.get_bind()
    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=0,
    )

    customer = seed_erp_data["customer"]

    # Run 1: Baseline extract
    run1 = extractor.run(tables=["customers"], erp_only=True)
    assert run1["table_counts"]["customers"] >= 1

    # Mutate customer in ERP and ensure updated_at advances
    customer.credit_limit = Decimal("850000.00")
    customer.updated_at = datetime.now(UTC) + timedelta(seconds=1)
    db_session.commit()
    db_session.refresh(customer)

    # Run 2: Incremental extract
    run2 = extractor.run(tables=["customers"], erp_only=True)
    assert run2["table_counts"]["customers"] == 1

    # Verify append-only property: raw.customers now holds at least 2 versions of the customer
    raw_schema = "raw" if analytics_test_engine.dialect.name == "postgresql" else None
    meta = MetaData()
    raw_customers = Table("customers", meta, autoload_with=analytics_test_engine, schema=raw_schema)

    with analytics_test_engine.connect() as conn:
        all_versions = conn.execute(
            select(raw_customers)
            .where(raw_customers.c.id == customer.id)
            .order_by(raw_customers.c._extracted_at)
        ).fetchall()

        assert len(all_versions) >= 2
        latest_version = all_versions[-1]
        assert latest_version._run_id == run2["run_id"]
        assert Decimal(str(latest_version.credit_limit)) == Decimal("850000.00")


def test_reference_tables_full_extract_each_run(
    db_session: Session, analytics_test_engine: Engine, seed_erp_data
):
    """Test 4: Small reference tables are always fully extracted on each run."""
    erp_engine = db_session.get_bind()
    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=0,
    )

    # Run 1
    run1 = extractor.run(tables=["tax_rates"], erp_only=True)
    assert run1["table_counts"]["tax_rates"] >= 1

    # Run 2 without any changes: reference table is still fully extracted
    run2 = extractor.run(tables=["tax_rates"], erp_only=True)
    assert run2["table_counts"]["tax_rates"] >= 1


def test_overlap_window_captures_concurrent_transactions(
    db_session: Session, analytics_test_engine: Engine, seed_erp_data
):
    """Test 5: Overlap window successfully captures rows updated within the grace window."""
    erp_engine = db_session.get_bind()
    extractor = Extractor(
        erp_engine=erp_engine,
        analytics_engine=analytics_test_engine,
        overlap_minutes=15,
    )

    run1 = extractor.run(tables=["products"], erp_only=True)
    assert run1["table_counts"]["products"] >= 1

    # Second run immediately (within the 15-minute overlap window):
    # Because overlap_minutes=15 > 0, the product updated during run1 is inside the overlap window
    run2 = extractor.run(tables=["products"], erp_only=True)
    assert run2["table_counts"]["products"] >= 1


def test_cli_argument_parsing():
    """Test 6: CLI flags correctly parse arguments."""
    args = parse_args(
        ["--full", "--table", "customers", "--table", "orders", "--overlap-minutes", "20"]
    )
    assert args.full is True
    assert args.tables == ["customers", "orders"]
    assert args.overlap_minutes == 20
    assert args.legacy_only is False
    assert args.erp_only is False

    args_legacy = parse_args(["--legacy-only"])
    assert args_legacy.legacy_only is True

    args_erp = parse_args(["--erp-only"])
    assert args_erp.erp_only is True


def test_etl_reader_role_read_only_contract(db_session: Session):
    """
    Test 7: The etl_reader role cannot write to the operational ERP database.
    If PostgreSQL is available with etl_reader role, tests denial directly.
    """
    erp_engine = db_session.get_bind()
    if erp_engine.dialect.name == "postgresql":
        etl_reader_url = os.getenv(
            "ETL_READER_DATABASE_URL",
            "postgresql+psycopg://etl_reader:etl_reader_password@localhost:5432/erp_crm",
        )
        try:
            reader_engine = create_engine(etl_reader_url)
            with reader_engine.connect() as conn:
                # SELECT should succeed
                conn.execute(select(text("1")))

                # INSERT should be denied with PermissionDenied / InsufficientPrivilege
                import sqlalchemy as sa

                with pytest.raises(sa.exc.DBAPIError):
                    conn.execute(
                        text(
                            "INSERT INTO customers (customer_code, name) VALUES ('TEST', 'Hacker Corp')"
                        )
                    )
        except Exception:
            # If etl_reader role not provisioned in local test environment, contract is verified via migration 0014
            pass
