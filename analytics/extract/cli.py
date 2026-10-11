"""
Extraction CLI (Roadmap §V1.1)
Command-line interface for running the extraction pipeline manually or via scheduled cron jobs.
Usage:
    python -m analytics.extract [--full] [--table customers] [--overlap-minutes 10]
"""

import argparse
import sys
import time

from analytics.extract.extractor import Extractor


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract operational ERP tables and legacy files into append-only raw analytics layer."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full refresh of all tables instead of incremental extraction.",
    )
    parser.add_argument(
        "--table",
        action="append",
        dest="tables",
        help="Specify one or more tables to extract (can be specified multiple times).",
    )
    parser.add_argument(
        "--overlap-minutes",
        type=int,
        default=None,
        help="Overlap window in minutes to catch long-running transactions (default: 10 min).",
    )
    parser.add_argument(
        "--legacy-only",
        action="store_true",
        help="Extract legacy CSV files only.",
    )
    parser.add_argument(
        "--erp-only",
        action="store_true",
        help="Extract ERP operational tables only.",
    )
    return parser.parse_args(args)


def main() -> int:
    args = parse_args()

    print("=" * 70)
    print("ERP/CRM Analytics Platform - Data Extraction Layer (V1.1)")
    print("=" * 70)
    print(f"Mode: {'Full Refresh' if args.full else 'Incremental (High-Watermark)'}")
    if args.tables:
        print(f"Target Tables: {', '.join(args.tables)}")
    if args.overlap_minutes is not None:
        print(f"Overlap Window: {args.overlap_minutes} minutes")
    print("-" * 70)

    t0 = time.time()
    try:
        extractor = Extractor(overlap_minutes=args.overlap_minutes)
        summary = extractor.run(
            tables=args.tables,
            full_refresh=args.full,
            legacy_only=args.legacy_only,
            erp_only=args.erp_only,
        )

        duration = time.time() - t0
        print(f"Extraction Completed Successfully in {duration:.2f}s!")
        print(f"ETL Run ID      : {summary['run_id']}")
        print(f"Total Rows      : {summary['rows_extracted']:,}")
        print("\nExtracted Table Breakdown:")
        for table, count in summary["table_counts"].items():
            print(f"  • {table:<25} : {count:>8,} rows")
        print("=" * 70)
        return 0

    except Exception as exc:  # noqa: BLE001
        duration = time.time() - t0
        print(
            f"\n[ERROR] Extraction failed after {duration:.2f}s: {exc}", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
