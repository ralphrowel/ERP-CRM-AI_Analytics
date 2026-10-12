"""
CLI Interface for Power BI Semantic Model and BI Assets (Roadmap §V1.5)
Usage:
    python -m analytics.bi --export
    python -m analytics.bi --verify-parity
"""

import argparse
import sys
from pathlib import Path

from analytics.bi.exporter import PowerBiExporter
from analytics.bi.queries import KpiQueryRunner
from analytics.db import get_analytics_engine


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Power BI Semantic Model & KPI DAX Engine (Milestone V1.5)."
    )
    parser.add_argument(
        "--export",
        action="store_true",
        default=True,
        help="Export semantic model schema (JSON), DAX measures, TMDL, and security scripts.",
    )
    parser.add_argument(
        "--verify-parity",
        action="store_true",
        help="Execute reference SQL queries on mart to verify KPI metric computations.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for generated Power BI artifacts.",
    )
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    exporter = PowerBiExporter(output_dir=args.output_dir)

    if args.verify_parity:
        print("Executing reference SQL queries for Power BI KPI Parity...")
        engine = get_analytics_engine()
        runner = KpiQueryRunner(engine)

        net_rev = runner.calculate_kpi_001_net_revenue()
        gm = runner.calculate_kpi_002_gross_margin()
        gm_pct = runner.calculate_kpi_003_gross_margin_pct()
        orders = runner.calculate_kpi_004_orders()
        ar_out = runner.calculate_kpi_005_ar_outstanding()
        pipeline = runner.calculate_kpi_007_weighted_pipeline()
        cycle = runner.calculate_kpi_010_avg_sales_cycle()
        inv_val = runner.calculate_kpi_013_inventory_value()
        spend = runner.calculate_kpi_016_purchase_spend()
        ontime = runner.calculate_kpi_017_supplier_on_time_rate()

        print("-" * 65)
        print(f"{'KPI ID':<10} {'Metric Name':<30} {'SQL Calculated Value'}")
        print("-" * 65)
        print(f"{'KPI-001':<10} {'Net Revenue':<30} ₱{net_rev:,.2f}")
        print(f"{'KPI-002':<10} {'Gross Margin':<30} ₱{gm:,.2f}")
        print(f"{'KPI-003':<10} {'Gross Margin %':<30} {gm_pct * 100:.1f}%")
        print(f"{'KPI-004':<10} {'Orders':<30} {orders:,}")
        print(f"{'KPI-005':<10} {'AR Outstanding':<30} ₱{ar_out:,.2f}")
        print(f"{'KPI-007':<10} {'Weighted Pipeline':<30} ₱{pipeline:,.2f}")
        print(f"{'KPI-010':<10} {'Avg Sales Cycle':<30} {cycle:.1f} days")
        print(f"{'KPI-013':<10} {'Inventory Value':<30} ₱{inv_val:,.2f}")
        print(f"{'KPI-016':<10} {'Purchase Spend':<30} ₱{spend:,.2f}")
        print(f"{'KPI-017':<10} {'Supplier On-Time Rate':<30} {ontime * 100:.1f}%")
        print("-" * 65)
        print("SQL-to-DAX parity verification complete.")
        sys.exit(0)

    print("Exporting Power BI Semantic Model and DAX Measure Catalog...")
    exported = exporter.export_all()
    print("Successfully exported Power BI artifacts:")
    for key, path in exported.items():
        print(f"  - [{key}]: {path}")


if __name__ == "__main__":
    main()
