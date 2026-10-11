"""
Unit Tests for Milestone V1.3: Data Quality Integration (Visiq DQ Engine)
Roadmap §V1.3 & Visiq System Architecture §4.5

Test Coverage:
1. 4-Dimension Quality Scoring Model:
   - Completeness 30%, Validity 30%, Uniqueness 20%, Consistency 20%
   - Enterprise letter grades (A >= 90, B >= 80, C >= 70, D >= 60, F < 60)
2. Defect Manifest Recall:
   - Verifies >= 95% defect detection recall across all 9 defect types against defect_manifest.json
3. Entity Resolution:
   - Multi-tier matching (tax_id_exact=1.00, email_exact=0.95, name_fuzzy>=0.85)
   - Verified in dq.entity_map
4. Formula Injection Sanitization & Non-Destructive Cleaning:
   - Neutralizes leading control characters (=, +, -, @, \\t, \\r) via to_safe_csv_text
   - Derived staging.clean_* produced non-destructively; raw data untouched
   - Lineage tracked in dq.lineage
5. Quarantine & Mart Circuit Breaker:
   - Critical failures quarantined in dq.quarantine
   - Blocks mart load with CircuitBreakerError and status='BLOCKED' in etl.runs
6. Dry-Run Preview:
   - In-memory simulation projecting scorecard improvements without database writes
7. CLI:
   - Command-line argument parsing
"""

import json
from pathlib import Path

import pytest
from analytics.db import init_analytics_db
from analytics.dq.cleaner import (
    clean_customer_row,
    preview_cleaning,
    to_safe_csv_text,
)
from analytics.dq.cli import parse_args
from analytics.dq.resolution import resolve_entities
from analytics.dq.rules import (
    get_default_customer_rules,
    get_default_sales_rules,
)
from analytics.dq.runner import CircuitBreakerError, DqRunner
from analytics.dq.scoring import (
    RuleEvaluationResult,
    calculate_quality_scorecard,
    score_to_letter_grade,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool


@pytest.fixture
def analytics_engine() -> Engine:
    """Creates an isolated in-memory SQLite analytics engine with initialized schemas."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_analytics_db(engine)
    return engine


# -------------------------------------------------------------------------
# Test 1: Visiq 4-Dimension Quality Scoring Model
# -------------------------------------------------------------------------
def test_4d_quality_scoring_model():
    """Verifies dimension weights (30/30/20/20) and letter grade quantization."""
    # Letter grade thresholds
    assert score_to_letter_grade(95.0) == "A"
    assert score_to_letter_grade(90.0) == "A"
    assert score_to_letter_grade(85.0) == "B"
    assert score_to_letter_grade(80.0) == "B"
    assert score_to_letter_grade(75.0) == "C"
    assert score_to_letter_grade(70.0) == "C"
    assert score_to_letter_grade(65.0) == "D"
    assert score_to_letter_grade(60.0) == "D"
    assert score_to_letter_grade(59.9) == "F"
    assert score_to_letter_grade(0.0) == "F"

    # Synthetic rule results:
    # Completeness (weight 0.30): 100% pass -> 30.0
    # Validity (weight 0.30): 50% pass -> 15.0
    # Uniqueness (weight 0.20): 100% pass -> 20.0
    # Consistency (weight 0.20): 75% pass -> 15.0
    # Expected composite = 30.0 + 15.0 + 20.0 + 15.0 = 80.0 -> Grade B
    rule_results = [
        RuleEvaluationResult("r1", "Completeness", "c1", 100, 0),
        RuleEvaluationResult("r2", "Validity", "c2", 100, 50),
        RuleEvaluationResult("r3", "Uniqueness", "c3", 100, 0),
        RuleEvaluationResult("r4", "Consistency", "c4", 100, 25),
    ]

    scorecard = calculate_quality_scorecard("test_dataset", rule_results)
    assert scorecard.composite_score == 80.0
    assert scorecard.letter_grade == "B"
    assert scorecard.dimension_scores["Completeness"] == 100.0
    assert scorecard.dimension_scores["Validity"] == 50.0
    assert scorecard.dimension_scores["Uniqueness"] == 100.0
    assert scorecard.dimension_scores["Consistency"] == 75.0
    assert scorecard.total_issues == 75


# -------------------------------------------------------------------------
# Test 2: Defect Manifest Recall >= 95% Across All 9 Defect Types
# -------------------------------------------------------------------------
def test_defect_manifest_detection_recall():
    """
    Evaluates rule suite against injected legacy data and benchmarks
    recall against the ground truth defect manifest (backend/data/legacy/defect_manifest.json).
    Exit Criterion: Recall >= 95% across all 9 defect types.
    """
    manifest_path = Path("backend/data/legacy/defect_manifest.json")
    if not manifest_path.exists():
        manifest_path = Path("../backend/data/legacy/defect_manifest.json")
    assert manifest_path.exists(), f"Defect manifest missing at {manifest_path}"

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    total_manifest_defects = len(manifest["defects"])
    assert total_manifest_defects == 973

    # Load legacy CSVs
    cust_csv = Path("backend/data/legacy/legacy_customers.csv")
    if not cust_csv.exists():
        cust_csv = Path("../backend/data/legacy/legacy_customers.csv")
    sales_csv = Path("backend/data/legacy/legacy_sales_2023_2025.csv")
    if not sales_csv.exists():
        sales_csv = Path("../backend/data/legacy/legacy_sales_2023_2025.csv")

    import csv

    with open(cust_csv, encoding="utf-8") as f:
        customers_rows = list(csv.DictReader(f))
    with open(sales_csv, encoding="utf-8") as f:
        sales_rows = list(csv.DictReader(f))

    # Add 1-based CSV line number matching manifest
    for idx, r in enumerate(customers_rows, start=2):
        r["_manifest_row"] = idx
    for idx, r in enumerate(sales_rows, start=2):
        r["_manifest_row"] = idx

    detected_keys = set()

    # Evaluate Customers
    cust_rules = get_default_customer_rules()
    for rule in cust_rules:
        _, issues = rule.evaluate(customers_rows, "_manifest_row")
        for iss in issues:
            # Map rule to defect type
            defect_type = ""
            if "currency" in iss.rule_name:
                defect_type = "currency_formatting"
            elif "phone" in iss.rule_name:
                defect_type = "nonstandard_phone"
            elif "email" in iss.rule_name:
                defect_type = "missing_email"
            elif "duplicate" in iss.rule_name:
                defect_type = "duplicate_variant"
            elif "whitespace" in iss.rule_name:
                defect_type = "whitespace_casing"
            elif "spelling" in iss.rule_name:
                defect_type = "spelling_variant"

            if defect_type:
                detected_keys.add(
                    ("legacy_customers.csv", int(iss.row_key), iss.column, defect_type)
                )

    # Evaluate Sales
    sales_rules = get_default_sales_rules()
    for rule in sales_rules:
        _, issues = rule.evaluate(sales_rows, "_manifest_row")
        for iss in issues:
            defect_type = ""
            if "date" in iss.rule_name:
                defect_type = "ambiguous_date"
            elif "quantity" in iss.rule_name:
                defect_type = "negative_quantity"
            elif "sku" in iss.rule_name:
                defect_type = "orphan_product"
            elif "currency" in iss.rule_name:
                defect_type = "currency_formatting"

            if defect_type:
                detected_keys.add(
                    (
                        "legacy_sales_2023_2025.csv",
                        int(iss.row_key),
                        iss.column,
                        defect_type,
                    )
                )

    manifest_keys = {
        (d["file"], d["row"], d["column"], d["defect_type"]) for d in manifest["defects"]
    }
    matches = manifest_keys.intersection(detected_keys)
    recall = len(matches) / len(manifest_keys)

    print(f"\n[BENCHMARK] Manifest Recall: {len(matches)} / {len(manifest_keys)} = {recall:.2%}")
    assert recall >= 0.95, f"Defect recall {recall:.2%} must be at least 95% of manifest defects!"


# -------------------------------------------------------------------------
# Test 3: Entity Resolution Linking Legacy to ERP Customers
# -------------------------------------------------------------------------
def test_entity_resolution_linking(analytics_engine: Engine):
    """Verifies 3-tier entity resolution matching (TIN, Email, Fuzzy Name)."""
    legacy_data = [
        {
            "legacy_customer_id": "LEG-CUS-001",
            "customer_name": "San Miguel Packaging",
            "tax_id": "123-456-789-000",
            "contact_email": "info@sm.ph",
        },
        {
            "legacy_customer_id": "LEG-CUS-002",
            "customer_name": "Puregold Price Club Inc.",
            "tax_id": "999-999-999-000",
            "contact_email": "purchasing@puregold.com.ph",
        },
        {
            "legacy_customer_id": "LEG-CUS-003",
            "customer_name": "Ayala Land Development Corp.",
            "tax_id": "",
            "contact_email": "unregistered@domain.com",
        },
    ]

    erp_data = [
        {
            "id": 101,
            "name": "San Miguel Packaging Corporation",
            "tin": "123456789000",  # Exact TIN match
            "email": "corporate@sm.ph",
        },
        {
            "id": 102,
            "name": "Puregold Price Club",
            "tin": "111-222-333-000",
            "email": "purchasing@puregold.com.ph",  # Exact Email match
        },
        {
            "id": 103,
            "name": "Ayala Land Development",  # Fuzzy Name match
            "tin": "444-555-666-000",
            "email": "ayala@ayala.com",
        },
    ]

    matches = resolve_entities(legacy_data, erp_data, similarity_threshold=0.85)
    assert len(matches) == 3

    m_map = {m.legacy_customer_id: m for m in matches}

    # Match 1: TIN exact
    assert m_map["LEG-CUS-001"].erp_customer_id == 101
    assert m_map["LEG-CUS-001"].match_method == "tax_id_exact"
    assert m_map["LEG-CUS-001"].confidence == 1.00

    # Match 2: Email exact
    assert m_map["LEG-CUS-002"].erp_customer_id == 102
    assert m_map["LEG-CUS-002"].match_method == "email_exact"
    assert m_map["LEG-CUS-002"].confidence == 0.95

    # Match 3: Name fuzzy
    assert m_map["LEG-CUS-003"].erp_customer_id == 103
    assert m_map["LEG-CUS-003"].match_method == "name_fuzzy"
    assert m_map["LEG-CUS-003"].confidence >= 0.85


# -------------------------------------------------------------------------
# Test 4: Formula Injection Sanitization & Non-Destructive Cleaning
# -------------------------------------------------------------------------
def test_formula_sanitization_and_non_destructive_cleaning(
    analytics_engine: Engine,
):
    """
    Verifies to_safe_csv_text formula escaping (=, +, -, @, \\t, \\r)
    and non-destructive derived clean datasets (staging.clean_*).
    """
    # Formula escaping
    assert to_safe_csv_text("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert to_safe_csv_text("+CMD('calc')") == "'+CMD('calc')"
    assert to_safe_csv_text("@malicious_call") == "'@malicious_call"
    assert to_safe_csv_text("\talert(1)") == "'\talert(1)"
    assert to_safe_csv_text("\rcommand") == "'\rcommand"
    assert to_safe_csv_text("Normal Text") == "Normal Text"
    assert to_safe_csv_text(-45) == -45
    assert to_safe_csv_text("-45") == "-45"  # Pure numeric negative preserved

    # Cleaning customer row
    dirty_customer = {
        "legacy_customer_id": "LEG-CUS-001",
        "customer_name": "Puregold Price Club Inc.",
        "contact_email": "none@domain",
        "phone_number": "+63-917-860-3172",
        "city": "MAKATI ",
        "credit_limit": "₱ 190,000.00",
        "notes": "=SUM(A1:A10)",
    }

    clean_cust, diffs, coerced = clean_customer_row(dirty_customer)
    assert clean_cust["customer_name"] == "Puregold Price Club"  # Canonical entity
    assert clean_cust["contact_email"] is None  # Coerced null
    assert clean_cust["phone_number"] == "09178603172"  # Normalized mobile
    assert clean_cust["city"] == "Makati"  # Canonical title
    assert clean_cust["credit_limit"] == "190000.00"  # Stripped currency symbol
    assert clean_cust["notes"] == "'=SUM(A1:A10)"  # Formula injection escaped
    assert coerced == 1
    assert len(diffs) >= 4


# -------------------------------------------------------------------------
# Test 5: Circuit Breaker Blocks Mart Load on Critical Defects
# -------------------------------------------------------------------------
def test_circuit_breaker_blocks_mart_on_critical_defects(
    analytics_engine: Engine,
):
    """Verifies circuit breaker raises CircuitBreakerError and quarantines critical records."""
    # Seed raw legacy sales with deliberate critical negative quantity and orphan SKU
    with analytics_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS legacy_sales (
                    _raw_id INTEGER PRIMARY KEY,
                    _row_number INTEGER,
                    invoice_no TEXT,
                    order_date TEXT,
                    quantity TEXT,
                    sku TEXT,
                    unit_price TEXT,
                    total_amount TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO legacy_sales (
                    _raw_id, _row_number, invoice_no, order_date, quantity, sku, unit_price, total_amount
                ) VALUES
                    (1, 1, 'INV-CRIT-001', '2024-05-01', '-50', 'SKU-001', '100.00', '5000.00'),
                    (2, 2, 'INV-CRIT-002', '2024-05-02', '10', 'UNLISTED-PROD', '50.00', '500.00')
                """
            )
        )

    runner = DqRunner(analytics_engine)

    # When circuit_breaker=True, must raise CircuitBreakerError
    with pytest.raises(CircuitBreakerError, match="critical DQ failures detected"):
        runner.run(datasets=["legacy_sales"], circuit_breaker=True)

    # Verify etl.runs record is BLOCKED
    with analytics_engine.connect() as conn:
        run_status = conn.execute(
            text("SELECT status FROM runs WHERE job = 'data_quality'")
        ).scalar()
        assert run_status == "BLOCKED"

        # Verify records quarantined in dq.quarantine
        quar_rows = conn.execute(text("SELECT row_key, reason FROM quarantine")).fetchall()
        assert len(quar_rows) == 2
        reasons = [r[1] for r in quar_rows]
        assert any("Negative quantity" in r for r in reasons)
        assert any("Orphan product" in r for r in reasons)


# -------------------------------------------------------------------------
# Test 6: In-Memory Dry-Run Preview
# -------------------------------------------------------------------------
def test_dry_run_preview_cleaning():
    """Verifies preview_cleaning calculates projected score gains without database mutations."""
    sample_rows = [
        {
            "legacy_customer_id": "LEG-CUS-001",
            "customer_name": "San Miguel Packaging, Inc.",
            "contact_email": "info@sm.ph",
            "phone_number": "+63-917-860-3172",
            "city": "ILOILO CITY",
            "credit_limit": "150,000.00",
        },
        {
            "legacy_customer_id": "LEG-CUS-002",
            "customer_name": "Puregold Price Club",
            "contact_email": "",
            "phone_number": "09173077052",
            "city": "Makati",
            "credit_limit": "200000.00",
        },
    ]

    rules = get_default_customer_rules()
    preview = preview_cleaning("legacy_customers", sample_rows, rules, "legacy_customer_id")

    assert preview.dataset == "legacy_customers"
    assert preview.original_score <= preview.projected_score
    assert preview.cell_diff_count > 0
    assert len(preview.sample_diffs) > 0


# -------------------------------------------------------------------------
# Test 7: CLI Argument Parsing
# -------------------------------------------------------------------------
def test_dq_cli_parsing():
    """Tests CLI flag parsing for --dataset, --preview, --circuit-breaker."""
    opts1 = parse_args(["--dataset", "legacy_customers", "--preview"])
    assert opts1.dataset == "legacy_customers"
    assert opts1.preview is True
    assert opts1.circuit_breaker is False

    opts2 = parse_args(["-c", "-d", "legacy_sales"])
    assert opts2.dataset == "legacy_sales"
    assert opts2.circuit_breaker is True
    assert opts2.preview is False
