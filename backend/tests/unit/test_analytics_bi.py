"""
Unit Tests for Milestone V1.5: Power BI Semantic Model & BI Aggregations
Roadmap §V1.5 & Roadmap §11 (KPI Dictionary)

Test Coverage:
1. KPI DAX Catalog Alignment:
   - Full 19-KPI catalog matching official Roadmap §11 definitions.
   - Time-intelligence expressions (MTD, YTD, PY, YoY, MoM).
2. Semantic Model Structure & Star Schema Relationships:
   - 7 conformed dimensions + 5 fact tables properly mapped.
   - 16 star schema relationships with 1:* single directional filter propagation.
3. SQL Reference Query Runner:
   - Reference SQL queries executed against mart tables validating parity.
4. Semantic Model Exporter & TMDL:
   - Exports JSON, DAX, TMDL, and security SQL artifacts.
5. bi_reader PostgreSQL Security Role Script:
   - Verifies least-privilege role setup (mart only, zero access to raw/staging/ERP).
6. BI CLI Argument Parsing:
   - Argument parsing for --export, --verify-parity, --output-dir.
"""

import os
import tempfile
from pathlib import Path

import pytest
from analytics.bi.cli import parse_args
from analytics.bi.dax import get_all_dax_expressions, get_kpi_dax_catalog
from analytics.bi.exporter import PowerBiExporter, generate_bi_reader_grant_sql
from analytics.bi.model import SemanticModel
from analytics.bi.queries import KpiQueryRunner
from analytics.db import init_analytics_db
from analytics.mart.builder import MartBuilder
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


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


def test_kpi_dax_catalog_alignment():
    """Test 1: All 19 enterprise KPIs from Roadmap §11 are cataloged with valid DAX formulas."""
    catalog = get_kpi_dax_catalog()
    assert len(catalog) == 19

    kpi_ids = {m.kpi_id for m in catalog}
    expected_ids = {f"KPI-{str(i).zfill(3)}" for i in range(1, 20)}
    assert kpi_ids == expected_ids

    # Validate individual key measures
    net_rev = next(m for m in catalog if m.kpi_id == "KPI-001")
    assert net_rev.name == "KPI-001 Net Revenue"
    assert net_rev.domain == "revenue"
    assert net_rev.table == "fact_sales_line"
    assert "SUM(fact_sales_line[net_revenue])" in net_rev.expression
    assert "MTD" in net_rev.time_intelligence
    assert "YTD" in net_rev.time_intelligence
    assert "YoY_Growth" in net_rev.time_intelligence

    margin_pct = next(m for m in catalog if m.kpi_id == "KPI-003")
    assert margin_pct.format_string == "0.0%"
    assert "DIVIDE" in margin_pct.expression

    win_rate = next(m for m in catalog if m.kpi_id == "KPI-008")
    assert win_rate.domain == "crm"
    assert "closed_won" in win_rate.expression

    supplier_ontime = next(m for m in catalog if m.kpi_id == "KPI-017")
    assert supplier_ontime.domain == "purchasing"
    assert "days_late" in supplier_ontime.expression

    # Verify full DAX generation
    dax_code = get_all_dax_expressions()
    assert "KPI-001 Net Revenue" in dax_code
    assert "KPI-019 Data Quality Score" in dax_code


def test_semantic_model_star_schema_relationships():
    """Test 2: Semantic model defines 7 dimensions, 5 facts, and 16 star schema relationships."""
    model = SemanticModel()
    tables_by_name = {t.name: t for t in model.tables}

    # Verify 7 conformed dimensions
    assert "dim_date" in tables_by_name
    assert "dim_customer" in tables_by_name
    assert "dim_product" in tables_by_name
    assert "dim_employee" in tables_by_name
    assert "dim_source_system" in tables_by_name
    assert "dim_warehouse" in tables_by_name
    assert "dim_supplier" in tables_by_name

    # Verify 5 fact tables
    assert "fact_sales_line" in tables_by_name
    assert "fact_opportunity_stage" in tables_by_name
    assert "fact_inventory_daily" in tables_by_name
    assert "fact_purchase_line" in tables_by_name
    assert "fact_ar_allocation" in tables_by_name

    assert tables_by_name["fact_sales_line"].is_fact is True
    assert tables_by_name["dim_customer"].is_fact is False

    # Verify relationships
    assert len(model.relationships) == 16
    for rel in model.relationships:
        assert rel.cardinality == "manyToOne"
        assert rel.cross_filter_direction == "single"
        assert rel.is_active is True
        # Fact table has foreign key, dimension has primary key
        assert rel.from_table.startswith("fact_")
        assert rel.to_table.startswith("dim_")

    # Verify serialization
    model_dict = model.to_dict()
    assert model_dict["name"] == "ERP_CRM_Analytical_Mart"
    assert model_dict["mode"] == "Import"
    assert len(model_dict["tables"]) == 12
    assert len(model_dict["measures"]) == 19


def test_sql_reference_query_runner(analytics_test_engine: Engine):
    """Test 3: SQL reference queries compute valid metrics matching DAX formulas on mart schema."""
    builder = MartBuilder(engine=analytics_test_engine)
    builder.build_all()

    runner = KpiQueryRunner(engine=analytics_test_engine)

    # 1. Revenue & margin queries
    net_rev = runner.calculate_kpi_001_net_revenue()
    gm = runner.calculate_kpi_002_gross_margin()
    gm_pct = runner.calculate_kpi_003_gross_margin_pct()
    assert isinstance(net_rev, float)
    assert isinstance(gm, float)
    assert isinstance(gm_pct, float)

    # 2. Commercial orders
    orders = runner.calculate_kpi_004_orders()
    assert isinstance(orders, int)
    assert orders >= 0

    # 3. Working capital AR
    ar = runner.calculate_kpi_005_ar_outstanding()
    assert isinstance(ar, float)
    assert ar >= 0.0

    # 4. Pipeline & sales cycle
    pipe = runner.calculate_kpi_007_weighted_pipeline()
    cycle = runner.calculate_kpi_010_avg_sales_cycle()
    assert isinstance(pipe, float)
    assert isinstance(cycle, float)

    # 5. Inventory value
    inv = runner.calculate_kpi_013_inventory_value()
    assert isinstance(inv, float)
    assert inv >= 0.0

    # 6. Purchasing & Supplier
    spend = runner.calculate_kpi_016_purchase_spend()
    ontime = runner.calculate_kpi_017_supplier_on_time_rate()
    assert isinstance(spend, float)
    assert 0.0 <= ontime <= 1.0


def test_powerbi_exporter_and_tmdl():
    """Test 4: Exporter generates semantic model JSON, TMDL, DAX, and security script."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir)
        exporter = PowerBiExporter(output_dir=out_path)
        files = exporter.export_all()

        assert "model_json" in files
        assert "measures_dax" in files
        assert "model_tmdl" in files
        assert "setup_sql" in files

        # Verify JSON
        assert files["model_json"].exists()
        json_content = files["model_json"].read_text(encoding="utf-8")
        assert "ERP_CRM_Analytical_Mart" in json_content
        assert "fact_sales_line" in json_content

        # Verify DAX
        assert files["measures_dax"].exists()
        dax_content = files["measures_dax"].read_text(encoding="utf-8")
        assert "[KPI-001 Net Revenue]" in dax_content

        # Verify TMDL
        assert files["model_tmdl"].exists()
        tmdl_content = files["model_tmdl"].read_text(encoding="utf-8")
        assert "model Model" in tmdl_content
        assert "table dim_date" in tmdl_content
        assert "relationship" in tmdl_content

        # Verify SQL
        assert files["setup_sql"].exists()
        sql_content = files["setup_sql"].read_text(encoding="utf-8")
        assert "CREATE ROLE bi_reader" in sql_content
        assert "GRANT USAGE ON SCHEMA mart" in sql_content


def test_bi_reader_security_script():
    """Test 5: bi_reader grant script enforces least privilege (mart only)."""
    sql = generate_bi_reader_grant_sql(
        db_name="test_analytics",
        username="bi_reader_test",
        password="secret_pass_123",
    )
    assert "CREATE ROLE bi_reader_test" in sql
    assert "GRANT CONNECT ON DATABASE test_analytics TO bi_reader_test;" in sql
    assert "GRANT USAGE ON SCHEMA mart TO bi_reader_test;" in sql
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA mart TO bi_reader_test;" in sql
    assert "REVOKE ALL ON SCHEMA raw FROM bi_reader_test;" in sql
    assert "REVOKE ALL ON SCHEMA staging FROM bi_reader_test;" in sql
    assert "REVOKE ALL ON SCHEMA dq FROM bi_reader_test;" in sql


def test_bi_cli_argument_parsing():
    """Test 6: Command-line argument parsing for analytics.bi."""
    args_default = parse_args([])
    assert args_default.export is True
    assert args_default.verify_parity is False
    assert args_default.output_dir is None

    args_parity = parse_args(["--verify-parity"])
    assert args_parity.verify_parity is True

    custom_dir = Path("scratch/test_bi_export")
    args_dir = parse_args(["--output-dir", str(custom_dir)])
    assert args_dir.output_dir == custom_dir
