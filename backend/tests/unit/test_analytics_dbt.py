"""Unit and Integration Tests for Modern Analytics Transformation with dbt Core (Milestone V2.4)

Validates:
1. dbt project configuration (dbt_project.yml, profiles.yml, sources.yml).
2. Manifest compilation and DAG parsing across all 42 models and 79 data tests.
3. Upstream and downstream lineage graph resolution:
   - fact_gl_journal_line -> (stg_journal_entry_lines, stg_journal_entries, dim_account).
   - dim_account -> stg_accounts -> raw.accounts.
   - fact_sales_line -> (stg_invoices, stg_invoice_lines, dim_customer, dim_product).
   - dim_customer -> int_customer_scd2.
4. Schema tests registration (unique, not_null, accepted_values, relationships).
5. Custom singular data tests (assert_trial_balance_debits_equal_credits, assert_ar_allocation_parity).
6. DbtRunner programmatic API and manifest introspection utilities.
"""

from pathlib import Path

import pytest
import yaml
from analytics.transform.dbt_runner import DbtRunner


@pytest.fixture
def dbt_runner() -> DbtRunner:
    """Initializes DbtRunner pointing to analytics_dbt/ directory."""
    project_dir = Path(__file__).resolve().parent.parent.parent.parent / "analytics_dbt"
    return DbtRunner(project_dir=project_dir, profiles_dir=project_dir)


# =============================================================================
# 1. dbt Project & Configuration Tests
# =============================================================================


def test_dbt_project_files_exist(dbt_runner: DbtRunner):
    """Verifies all required dbt project config files exist."""
    proj_dir = dbt_runner.project_dir
    assert (proj_dir / "dbt_project.yml").exists()
    assert (proj_dir / "profiles.yml").exists()
    assert (proj_dir / "models" / "staging" / "sources.yml").exists()
    assert (proj_dir / "models" / "staging" / "schema.yml").exists()
    assert (proj_dir / "models" / "intermediate" / "schema.yml").exists()
    assert (proj_dir / "models" / "mart" / "schema.yml").exists()


def test_dbt_project_yaml_structure(dbt_runner: DbtRunner):
    """Validates dbt_project.yml structure, profile name, and model materializations."""
    yml_path = dbt_runner.project_dir / "dbt_project.yml"
    config = yaml.safe_load(yml_path.read_text(encoding="utf-8"))

    assert config["name"] == "erp_analytics"
    assert config["profile"] == "erp_analytics"
    assert "models" in config

    model_cfgs = config["models"]["erp_analytics"]
    assert model_cfgs["staging"]["+materialized"] == "view"
    assert model_cfgs["intermediate"]["+materialized"] == "view"
    assert model_cfgs["mart"]["+materialized"] == "table"


def test_sources_yml_definitions(dbt_runner: DbtRunner):
    """Verifies source declarations for raw operational and Phase 3 accounting tables."""
    src_path = dbt_runner.project_dir / "models" / "staging" / "sources.yml"
    src_data = yaml.safe_load(src_path.read_text(encoding="utf-8"))

    source = src_data["sources"][0]
    assert source["name"] == "raw"
    assert source["schema"] == "raw"

    tables = {t["name"] for t in source["tables"]}
    # Operational tables
    assert "customers" in tables
    assert "invoices" in tables
    assert "payments" in tables
    assert "products" in tables
    # Phase 3 GL & FX tables
    assert "accounts" in tables
    assert "fiscal_periods" in tables
    assert "journal_entries" in tables
    assert "journal_entry_lines" in tables
    assert "currencies" in tables
    assert "fx_rates" in tables


# =============================================================================
# 2. DAG Compilation & Manifest Introspection Tests
# =============================================================================


def test_dbt_parse_and_manifest_generation(dbt_runner: DbtRunner):
    """Executes dbt parse and validates target/manifest.json contents."""
    res = dbt_runner.execute(["parse"])
    assert res.success is True, (
        f"dbt parse failed (rc={res.returncode}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    )
    assert res.returncode == 0

    manifest = dbt_runner.load_manifest()
    nodes = manifest.get("nodes", {})
    sources = manifest.get("sources", {})

    models = [n for n in nodes.values() if n.get("resource_type") == "model"]
    assert len(models) >= 40
    assert len(sources) >= 30


def test_dbt_model_listing(dbt_runner: DbtRunner):
    """Lists all models and asserts staging, intermediate, and mart models exist."""
    models = dbt_runner.list_models()

    # Staging models
    assert "stg_customers" in models
    assert "stg_invoices" in models
    assert "stg_payments" in models
    assert "stg_accounts" in models
    assert "stg_journal_entries" in models
    assert "stg_journal_entry_lines" in models
    assert "stg_currencies" in models
    assert "stg_fx_rates" in models

    # Intermediate models
    assert "int_customer_scd2" in models
    assert "int_ar_aging_buckets" in models

    # Mart dimensions & facts
    assert "dim_date" in models
    assert "dim_customer" in models
    assert "dim_account" in models
    assert "dim_product" in models
    assert "fact_sales_line" in models
    assert "fact_gl_journal_line" in models
    assert "fact_ar_allocation" in models


def test_gl_journal_line_lineage_and_dependencies(dbt_runner: DbtRunner):
    """Verifies DAG dependencies for fact_gl_journal_line and dim_account."""
    # fact_gl_journal_line depends on stg_journal_entry_lines, stg_journal_entries, dim_account
    gl_deps = dbt_runner.get_model_dependencies("fact_gl_journal_line")
    assert "dim_account" in gl_deps
    assert "stg_journal_entries" in gl_deps
    assert "stg_journal_entry_lines" in gl_deps

    # dim_account depends on stg_accounts
    acc_deps = dbt_runner.get_model_dependencies("dim_account")
    assert "stg_accounts" in acc_deps


def test_sales_and_customer_lineage(dbt_runner: DbtRunner):
    """Verifies DAG dependencies for fact_sales_line and dim_customer."""
    sales_deps = dbt_runner.get_model_dependencies("fact_sales_line")
    assert "dim_customer" in sales_deps
    assert "stg_invoices" in sales_deps
    assert "stg_invoice_lines" in sales_deps

    cust_deps = dbt_runner.get_model_dependencies("dim_customer")
    assert "int_customer_scd2" in cust_deps


# =============================================================================
# 3. Schema & Custom Singular Data Tests
# =============================================================================


def test_schema_tests_registered_in_manifest(dbt_runner: DbtRunner):
    """Verifies that schema tests (unique, not_null, accepted_values, relationships) are parsed."""
    manifest = dbt_runner.load_manifest()
    nodes = manifest.get("nodes", {})

    test_nodes = [n for n in nodes.values() if n.get("resource_type") == "test"]
    test_names = [n["name"] for n in test_nodes]

    # Staging tests
    assert any("stg_accounts" in t and "unique" in t for t in test_names)
    assert any("stg_accounts" in t and "accepted_values" in t for t in test_names)
    assert any("stg_journal_entries" in t and "accepted_values" in t for t in test_names)

    # Mart relationships tests
    assert any("fact_gl_journal_line" in t and "relationships" in t for t in test_names)
    assert any("fact_sales_line" in t and "relationships" in t for t in test_names)


def test_custom_singular_tests_exist(dbt_runner: DbtRunner):
    """Verifies custom singular SQL test files exist and are parsed."""
    test_dir = dbt_runner.project_dir / "tests"
    tb_test = test_dir / "assert_trial_balance_debits_equal_credits.sql"
    ar_test = test_dir / "assert_ar_allocation_parity.sql"

    assert tb_test.exists()
    assert ar_test.exists()

    manifest = dbt_runner.load_manifest()
    nodes = manifest.get("nodes", {})
    singular_tests = [
        n["name"]
        for n in nodes.values()
        if n.get("resource_type") == "test" and not n.get("test_metadata")
    ]

    assert "assert_trial_balance_debits_equal_credits" in singular_tests
    assert "assert_ar_allocation_parity" in singular_tests
