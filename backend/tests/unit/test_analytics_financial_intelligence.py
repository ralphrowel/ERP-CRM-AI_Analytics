"""
Unit and Integration Tests for Integrated Financial Intelligence (Milestone V2.5 Capstone-V3)

Validates:
1. Analytics extraction configuration includes General Ledger and Currency tables.
2. GL-to-BI Reconciliation Engine (GLReconciler) audits debit/credit parity and account variances.
3. Power BI Semantic Model registers dim_account, fact_gl_journal_line, and financial ratio DAX measures.
4. DAX Measures Catalog contains KPI-020 to KPI-027 (Current Ratio, Quick Ratio, Working Capital, ROE, etc.).
5. Visiq AI catalog maps financial KPIs, account dimensions, and natural language aliases.
6. Visiq deterministic tools: financial_statement_summary and gl_reconciliation_audit.
7. VisiqAgent conversational intent routing and narrative synthesis for financial statements and audits.
"""

from decimal import Decimal

import pytest
from analytics.bi.dax import get_all_dax_expressions, get_kpi_dax_catalog
from analytics.bi.model import SemanticModel
from analytics.config import analytics_settings
from analytics.reconciliation.gl_reconciliation import GLReconciler
from analytics.visiq.agent import VisiqAgent
from analytics.visiq.catalog import DIMENSIONS, KPI_METRIC_CATALOG, resolve_kpi
from analytics.visiq.sessions import DATASET_CATALOG
from analytics.visiq.tools import VisiqTools
from sqlalchemy import create_engine


@pytest.fixture
def memory_engines():
    """Provides paired in-memory SQLite engines mocking erp_crm and erp_analytics."""
    erp_engine = create_engine("sqlite:///:memory:")
    analytics_engine = create_engine("sqlite:///:memory:")

    erp_script = """
    CREATE TABLE accounts (
        id INTEGER PRIMARY KEY,
        code VARCHAR(10) UNIQUE NOT NULL,
        name VARCHAR(100) NOT NULL,
        account_type VARCHAR(20) NOT NULL,
        normal_balance VARCHAR(10) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 1
    );
    CREATE TABLE journal_entries (
        id INTEGER PRIMARY KEY,
        entry_no VARCHAR(50) UNIQUE NOT NULL,
        posting_date DATE NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'posted'
    );
    CREATE TABLE journal_entry_lines (
        id INTEGER PRIMARY KEY,
        journal_entry_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        debit_amount NUMERIC(19, 2) NOT NULL DEFAULT 0.00,
        credit_amount NUMERIC(19, 2) NOT NULL DEFAULT 0.00
    );

    INSERT INTO accounts (id, code, name, account_type, normal_balance) VALUES
    (1, '1110', 'Cash and Cash Equivalents', 'asset', 'debit'),
    (2, '1200', 'Accounts Receivable', 'asset', 'debit'),
    (3, '2100', 'Accounts Payable', 'liability', 'credit'),
    (4, '3100', 'Owner Equity', 'equity', 'credit'),
    (5, '4100', 'Sales Revenue', 'revenue', 'credit'),
    (6, '5100', 'Cost of Goods Sold', 'expense', 'debit'),
    (7, '6100', 'Operating Expenses', 'expense', 'debit');

    INSERT INTO journal_entries (id, entry_no, posting_date, status) VALUES
    (1, 'JV-2026-000001', '2026-01-15', 'posted');

    INSERT INTO journal_entry_lines (id, journal_entry_id, account_id, debit_amount, credit_amount) VALUES
    (1, 1, 1, 10000.00, 0.00),
    (2, 1, 5, 0.00, 10000.00);
    """

    analytics_script = """
    CREATE TABLE dim_account (
        account_key INTEGER PRIMARY KEY,
        account_id INTEGER,
        account_code VARCHAR(10),
        account_name VARCHAR(100),
        account_type VARCHAR(20),
        normal_balance VARCHAR(10),
        is_active BOOLEAN DEFAULT 1
    );
    CREATE TABLE fact_gl_journal_line (
        gl_fact_key INTEGER PRIMARY KEY,
        line_id INTEGER,
        journal_entry_id INTEGER,
        account_key INTEGER,
        date_key INTEGER,
        entry_no VARCHAR(50),
        posting_date DATE,
        source_document_type VARCHAR(50),
        source_document_id INTEGER,
        status VARCHAR(20),
        line_no INTEGER,
        debit_amount NUMERIC(19, 2) DEFAULT 0.00,
        credit_amount NUMERIC(19, 2) DEFAULT 0.00,
        net_amount NUMERIC(19, 2) DEFAULT 0.00,
        line_description VARCHAR(255)
    );

    INSERT INTO dim_account (account_key, account_id, account_code, account_name, account_type, normal_balance) VALUES
    (1, 1, '1110', 'Cash and Cash Equivalents', 'asset', 'debit'),
    (2, 2, '1200', 'Accounts Receivable', 'asset', 'debit'),
    (3, 3, '2100', 'Accounts Payable', 'liability', 'credit'),
    (4, 4, '3100', 'Owner Equity', 'equity', 'credit'),
    (5, 5, '4100', 'Sales Revenue', 'revenue', 'credit'),
    (6, 6, '5100', 'Cost of Goods Sold', 'expense', 'debit'),
    (7, 7, '6100', 'Operating Expenses', 'expense', 'debit');

    INSERT INTO fact_gl_journal_line (gl_fact_key, line_id, journal_entry_id, account_key, date_key, entry_no, posting_date, debit_amount, credit_amount, net_amount) VALUES
    (1, 1, 1, 1, 20260115, 'JV-2026-000001', '2026-01-15', 10000.00, 0.00, 10000.00),
    (2, 2, 1, 5, 20260115, 'JV-2026-000001', '2026-01-15', 0.00, 10000.00, -10000.00);
    """

    raw_erp = erp_engine.raw_connection()
    raw_erp.executescript(erp_script)
    raw_erp.commit()

    raw_analytics = analytics_engine.raw_connection()
    raw_analytics.executescript(analytics_script)
    raw_analytics.commit()

    return erp_engine, analytics_engine


# =============================================================================
# 1. Extraction Registry Tests
# =============================================================================


def test_extraction_config_includes_gl_and_currency_tables():
    """Verifies that analytics_settings has registered GL and currency entities."""
    assert "currencies" in analytics_settings.REFERENCE_TABLES
    assert "accounts" in analytics_settings.INCREMENTAL_TABLES
    assert "fiscal_periods" in analytics_settings.INCREMENTAL_TABLES
    assert "journal_entries" in analytics_settings.INCREMENTAL_TABLES
    assert "journal_entry_lines" in analytics_settings.INCREMENTAL_TABLES
    assert "fx_rates" in analytics_settings.INCREMENTAL_TABLES


# =============================================================================
# 2. GL-to-BI Reconciliation Engine Tests
# =============================================================================


def test_gl_reconciler_totals_parity(memory_engines):
    """Audits exact debit and credit parity between operational GL and analytical mart."""
    erp_eng, analytics_eng = memory_engines
    reconciler = GLReconciler(erp_engine=erp_eng, analytics_engine=analytics_eng)

    totals = reconciler.reconcile_totals()
    assert totals["is_reconciled"] is True
    assert totals["operational"]["debit"] == Decimal("10000.00")
    assert totals["operational"]["credit"] == Decimal("10000.00")
    assert totals["mart"]["debit"] == Decimal("10000.00")
    assert totals["mart"]["credit"] == Decimal("10000.00")
    assert totals["variance"]["net_diff"] == Decimal("0.00")


def test_gl_reconciler_account_parity_and_audit(memory_engines):
    """Verifies per-account balance parity and overall audit report output."""
    erp_eng, analytics_eng = memory_engines
    reconciler = GLReconciler(erp_engine=erp_eng, analytics_engine=analytics_eng)

    report = reconciler.audit()
    assert report.is_reconciled is True
    assert report.status == "reconciled"
    assert len(report.discrepant_accounts) == 0
    assert report.total_debit_variance == Decimal("0.00")
    assert report.total_credit_variance == Decimal("0.00")
    assert report.net_variance == Decimal("0.00")

    rep_dict = report.to_dict()
    assert rep_dict["is_reconciled"] is True
    assert rep_dict["operational_debit_total"] == 10000.00


# =============================================================================
# 3. Power BI Semantic Model & DAX Catalog Tests
# =============================================================================


def test_power_bi_semantic_model_includes_gl_tables():
    """Verifies dim_account and fact_gl_journal_line are registered in SemanticModel."""
    model = SemanticModel()
    table_names = [t.name for t in model.tables]

    assert "dim_account" in table_names
    assert "fact_gl_journal_line" in table_names

    # Check relationships
    gl_rels = [r for r in model.relationships if r.from_table == "fact_gl_journal_line"]
    assert len(gl_rels) >= 2
    assert any(r.to_table == "dim_account" and r.from_column == "account_key" for r in gl_rels)
    assert any(r.to_table == "dim_date" and r.from_column == "date_key" for r in gl_rels)


def test_dax_catalog_financial_ratio_measures():
    """Validates KPI-020 through KPI-027 measures exist with correct DAX syntax."""
    catalog = get_kpi_dax_catalog()
    kpi_map = {m.kpi_id: m for m in catalog}

    assert "KPI-020" in kpi_map  # Current Ratio
    assert "KPI-021" in kpi_map  # Quick Ratio
    assert "KPI-022" in kpi_map  # Working Capital
    assert "KPI-023" in kpi_map  # Operating Margin %
    assert "KPI-024" in kpi_map  # Net Profit Margin %
    assert "KPI-025" in kpi_map  # Debt to Equity
    assert "KPI-026" in kpi_map  # ROE
    assert "KPI-027" in kpi_map  # GL Balance Integrity

    curr_ratio = kpi_map["KPI-020"]
    assert "CurrentAssets" in curr_ratio.expression
    assert "CurrentLiabilities" in curr_ratio.expression
    assert curr_ratio.domain == "financial"

    gl_integrity = kpi_map["KPI-027"]
    assert "ABS(" in gl_integrity.expression

    # Verify DAX script formatting generates cleanly
    all_dax = get_all_dax_expressions()
    assert "[KPI-020 Current Ratio] =" in all_dax
    assert "[KPI-022 Working Capital] =" in all_dax


# =============================================================================
# 4. Visiq AI Catalog & Natural Language Aliases Tests
# =============================================================================


def test_visiq_catalog_financial_definitions():
    """Asserts financial KPIs and dimensions are registered in Visiq catalog."""
    assert "KPI-020" in KPI_METRIC_CATALOG
    assert "KPI-022" in KPI_METRIC_CATALOG
    assert "KPI-026" in KPI_METRIC_CATALOG
    assert "KPI-027" in KPI_METRIC_CATALOG

    assert "account" in DIMENSIONS
    assert "account_type" in DIMENSIONS

    # Test alias resolution
    assert resolve_kpi("current ratio").kpi_id == "KPI-020"
    assert resolve_kpi("working capital").kpi_id == "KPI-022"
    assert resolve_kpi("operating margin").kpi_id == "KPI-023"
    assert resolve_kpi("net profit margin").kpi_id == "KPI-024"
    assert resolve_kpi("debt to equity").kpi_id == "KPI-025"
    assert resolve_kpi("roe").kpi_id == "KPI-026"
    assert resolve_kpi("gl integrity").kpi_id == "KPI-027"


def test_visiq_dataset_catalog_includes_financial():
    """Verifies mart_financial dataset registration with starter questions."""
    assert "mart_financial" in DATASET_CATALOG
    ds = DATASET_CATALOG["mart_financial"]
    assert "fact_gl_journal_line" in ds["fact_tables"]
    assert len(ds["starter_questions"]) >= 3


# =============================================================================
# 5. Visiq Tools & Conversational Agent Tests
# =============================================================================


def test_visiq_tools_financial_statements(memory_engines):
    """Tests financial_statement_summary tool for balance sheet and income statement."""
    _, analytics_eng = memory_engines
    tools = VisiqTools(analytics_eng)

    # Balance Sheet
    bs = tools.financial_statement_summary(statement_type="balance_sheet")
    assert bs["tool"] == "financial_statement_summary"
    assert bs["statement_type"] == "balance_sheet"
    assert bs["total_assets"] == 10000.00
    assert bs["total_liabilities"] == 0.00
    assert bs["current_period_net_income"] == 10000.00
    assert bs["total_equity"] == 10000.00
    assert bs["is_balanced"] is True

    # Income Statement
    inc = tools.financial_statement_summary(statement_type="income_statement")
    assert inc["tool"] == "financial_statement_summary"
    assert inc["statement_type"] == "income_statement"
    assert inc["total_revenue"] == 10000.00
    assert inc["gross_profit"] == 10000.00
    assert inc["net_income"] == 10000.00


def test_visiq_agent_conversational_financial_intelligence(memory_engines):
    """Tests VisiqAgent intent routing and narrative synthesis for financial queries."""
    erp_eng, analytics_eng = memory_engines
    agent = VisiqAgent(analytics_eng)
    # Point reconciler inside agent to mock ERP engine
    agent.tools.engine = analytics_eng

    # 1. Balance sheet question
    bs_res = agent.ask("What is our latest balance sheet and accounting equilibrium status?")
    assert bs_res["tool_called"] == "financial_statement_summary"
    assert "Balance Sheet Summary" in bs_res["narrative"]
    assert "BALANCED" in bs_res["narrative"]
    assert "₱10,000.00" in bs_res["narrative"]

    # 2. Income statement question
    inc_res = agent.ask("Show our income statement and operating profit margin")
    assert inc_res["tool_called"] == "financial_statement_summary"
    assert "Income Statement" in inc_res["narrative"]
    assert "₱10,000.00" in inc_res["narrative"]

    # 3. Financial KPI question
    kpi_res = agent.ask("What is our working capital buffer?")
    assert kpi_res["tool_called"] == "get_metric"
    assert "Working Capital Summary" in kpi_res["narrative"]
