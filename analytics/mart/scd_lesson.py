"""
SCD Type 2 Discovery Lesson (Roadmap §V1.4)
Executes the discovery experiment demonstrating the flaw of SCD Type 1 (overwrite)
versus the historical integrity of SCD Type 2 (effective dating and surrogate keys).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, text


def run_scd_discovery_lesson(engine: Engine) -> dict[str, Any]:
    """
    Executes the SCD Type 1 vs SCD Type 2 demonstration experiment:
    1. Customer is created in 'Luzon'.
    2. 2024 Invoice line of 100,000 PHP is recorded.
    3. Type 1 Overwrite: Customer moves to 'Visayas'; historical 2024 report shifts to Visayas!
    4. Type 2 Effective Dating: History row preserved for Luzon; new row for Visayas.
    5. Type 2 Report: 2024 sales remain in Luzon; 2025 sales in Visayas.
    """
    is_postgres = engine.dialect.name == "postgresql"
    qual_cust = "mart.dim_customer" if is_postgres else "dim_customer"
    qual_fact = "mart.fact_sales_line" if is_postgres else "fact_sales_line"

    results: dict[str, Any] = {}

    with engine.begin() as conn:
        # Clean test customer & fact rows
        conn.execute(
            text(
                f"DELETE FROM {qual_fact} WHERE invoice_no IN ('INV-SCD-2024', 'INV-SCD-2025');"
            )
        )
        conn.execute(text(f"DELETE FROM {qual_cust} WHERE customer_id = 9999;"))

        # Step 1: Insert Customer under Type 1 state (Region: Luzon)
        conn.execute(
            text(
                f"""
                INSERT INTO {qual_cust} (
                    customer_id, customer_no, name, region, valid_from, valid_to, is_current
                ) VALUES (
                    9999, 'CUS-SCD-9999', 'Atlas Discovery Corp', 'Luzon', :vf, NULL, 1
                )
                """
            ),
            {"vf": datetime(2023, 1, 1, tzinfo=UTC)},
        )
        c_key_luzon = conn.execute(
            text(f"SELECT customer_key FROM {qual_cust} WHERE customer_id = 9999")
        ).scalar()

        # Step 2: Insert 2024 Invoice of 100,000 PHP
        conn.execute(
            text(
                f"""
                INSERT INTO {qual_fact} (
                    date_key, customer_key, product_key, employee_key, source_system_key,
                    invoice_no, document_type, source_system, line_number,
                    quantity, unit_price, gross, discount, net_revenue, tax, cogs, gross_margin
                ) VALUES (
                    20240615, :ck, 1, 1, 1,
                    'INV-SCD-2024', 'invoice', 'erp', 1,
                    1, 100000.0, 100000.0, 0.0, 100000.0, 0.0, 40000.0, 60000.0
                )
                """
            ),
            {"ck": c_key_luzon},
        )

        # Baseline: Query 2024 sales by region
        q_sales = f"""
        SELECT c.region, SUM(f.net_revenue) AS total_revenue
        FROM {qual_fact} f
        JOIN {qual_cust} c ON f.customer_key = c.customer_key
        WHERE f.invoice_no = 'INV-SCD-2024'
        GROUP BY c.region
        """
        baseline = {r[0]: float(r[1]) for r in conn.execute(text(q_sales)).fetchall()}
        results["baseline_2024"] = baseline

        # Step 3: SCD Type 1 Overwrite Simulation
        # Customer moves to 'Visayas' in 2025; Type 1 updates row in-place!
        conn.execute(
            text(
                f"""
                UPDATE {qual_cust}
                SET region = 'Visayas'
                WHERE customer_id = 9999
                """
            )
        )
        type1_report = {
            r[0]: float(r[1]) for r in conn.execute(text(q_sales)).fetchall()
        }
        results["type1_flaw_2024_report"] = type1_report

        # Step 4: SCD Type 2 Fix
        # Reset row 1 to Luzon, valid until 2025-01-01, is_current = 0
        conn.execute(
            text(
                f"""
                UPDATE {qual_cust}
                SET region = 'Luzon', valid_to = :vt, is_current = 0
                WHERE customer_key = :ck
                """
            ),
            {"vt": datetime(2025, 1, 1, tzinfo=UTC), "ck": c_key_luzon},
        )
        # Insert new Type 2 record for Visayas, valid from 2025-01-01, is_current = 1
        conn.execute(
            text(
                f"""
                INSERT INTO {qual_cust} (
                    customer_id, customer_no, name, region, valid_from, valid_to, is_current
                ) VALUES (
                    9999, 'CUS-SCD-9999', 'Atlas Discovery Corp', 'Visayas', :vf, NULL, 1
                )
                """
            ),
            {"vf": datetime(2025, 1, 1, tzinfo=UTC)},
        )
        c_key_visayas = conn.execute(
            text(
                f"SELECT customer_key FROM {qual_cust} WHERE customer_id = 9999 AND is_current = 1"
            )
        ).scalar()

        # Insert 2025 Invoice of 50,000 PHP under the new Visayas key
        conn.execute(
            text(
                f"""
                INSERT INTO {qual_fact} (
                    date_key, customer_key, product_key, employee_key, source_system_key,
                    invoice_no, document_type, source_system, line_number,
                    quantity, unit_price, gross, discount, net_revenue, tax, cogs, gross_margin
                ) VALUES (
                    20250320, :ck, 1, 1, 1,
                    'INV-SCD-2025', 'invoice', 'erp', 1,
                    1, 50000.0, 50000.0, 0.0, 50000.0, 0.0, 20000.0, 30000.0
                )
                """
            ),
            {"ck": c_key_visayas},
        )

        # Step 5: Type 2 Queries
        q_both_years = f"""
        SELECT c.region,
               SUM(CASE WHEN f.date_key < 20250101 THEN f.net_revenue ELSE 0 END) AS rev_2024,
               SUM(CASE WHEN f.date_key >= 20250101 THEN f.net_revenue ELSE 0 END) AS rev_2025
        FROM {qual_fact} f
        JOIN {qual_cust} c ON f.customer_key = c.customer_key
        WHERE f.invoice_no IN ('INV-SCD-2024', 'INV-SCD-2025')
        GROUP BY c.region
        """
        type2_report = {
            r[0]: {"rev_2024": float(r[1]), "rev_2025": float(r[2])}
            for r in conn.execute(text(q_both_years)).fetchall()
        }
        results["customer_name"] = "Atlas Discovery Corp"
        results["original_region"] = "Luzon"
        results["updated_region"] = "Visayas"
        results["sales_2024_baseline"] = baseline
        results["sales_2024_after_type1"] = type1_report
        results["sales_2024_under_type2"] = {
            k: v["rev_2024"] for k, v in type2_report.items() if v["rev_2024"] > 0
        }
        results["sales_2025_under_type2"] = {
            k: v["rev_2025"] for k, v in type2_report.items() if v["rev_2025"] > 0
        }
        results["type2_preserved_report"] = type2_report

    return results
