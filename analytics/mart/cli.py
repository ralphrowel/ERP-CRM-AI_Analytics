"""
Command Line Interface for Analytical Data Mart Star Schema (Roadmap §V1.4)
Usage:
    python -m analytics.mart --build
    python -m analytics.mart --scd-lesson
    python -m analytics.mart --check-grains
"""

import argparse
import sys
from typing import Any

from analytics.db import get_analytics_engine
from analytics.mart.builder import MartBuilder
from analytics.mart.scd_lesson import run_scd_discovery_lesson


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and verify Analytical Data Mart Star Schema (Milestone V1.4)."
    )
    parser.add_argument(
        "--build",
        action="store_true",
        default=True,
        help="Build conformed dimensions, surrogate keys, facts, and verify grain (default: True).",
    )
    parser.add_argument(
        "--scd-lesson",
        action="store_true",
        help="Run the SCD Type 1 vs Type 2 discovery lesson demonstration.",
    )
    parser.add_argument(
        "--check-grains",
        action="store_true",
        help="Run grain uniqueness verification across all 5 fact tables.",
    )
    parser.add_argument(
        "--job-name",
        default="mart_build",
        help="ETL run job name for audit tracking in etl.runs (default: mart_build).",
    )
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    engine = get_analytics_engine()
    builder = MartBuilder(engine=engine)

    if args.scd_lesson:
        print("Running SCD Type 2 Discovery Lesson...")
        lesson_res = run_scd_discovery_lesson(engine=engine)
        print("\n=== SCD Discovery Lesson Results ===")
        print(f"Customer Name: {lesson_res['customer_name']}")
        print(f"Original Region: {lesson_res['original_region']}")
        print(f"Updated Region:  {lesson_res['updated_region']}")
        print(f"2024 Sales (Baseline): {lesson_res['sales_2024_baseline']}")
        print(f"2024 Sales (Type 1 Overwrite): {lesson_res['sales_2024_after_type1']}")
        print(f"2024 Sales (Type 2 History):   {lesson_res['sales_2024_under_type2']}")
        print(f"2025 Sales (Type 2 Current):   {lesson_res['sales_2025_under_type2']}")
        print("=== Discovery Lesson Completed Successfully ===")
        sys.exit(0)

    if args.check_grains:
        print("Checking grain uniqueness across all fact tables...")
        grains = builder.verify_grain_uniqueness()
        all_passed = True
        for fact_name, res in grains.items():
            status = "PASSED" if res["passed"] else "FAILED"
            if not res["passed"]:
                all_passed = False
            print(
                f"- {fact_name} (Grain: {res['grain']}): {status} (Rows: {res['row_count']})"
            )
        if not all_passed:
            print(
                "ERROR: One or more fact tables failed grain uniqueness verification!"
            )
            sys.exit(1)
        print("All fact table grains verified unique!")
        sys.exit(0)

    print("Building Analytical Data Mart (Star Schema)...")
    summary: dict[str, Any] = builder.build_all(job_name=args.job_name)

    print(
        f"\nMart Build Run #{summary['run_id']} finished with status: {summary['status'].upper()}"
    )
    print("-" * 75)
    print("Dimensions Built:")
    for dim_name, count in summary.get("dimensions", {}).items():
        print(f"  - {dim_name:<25}: {count} rows")
    print("\nFacts Built:")
    for fact_name, count in summary.get("facts", {}).items():
        print(f"  - {fact_name:<25}: {count} rows")
    print("-" * 75)
    print("Fact Table Grain Verification:")
    all_passed = True
    for fact_name, g_res in summary.get("grain_verification", {}).items():
        status = "PASSED" if g_res["passed"] else "FAILED"
        if not g_res["passed"]:
            all_passed = False
        print(f"  - {fact_name:<25}: {status} (Grain: {g_res['grain']})")

    if not all_passed:
        print("WARNING: Grain verification detected duplicates!")
        sys.exit(1)

    print("\nStar schema successfully built and verified.")


if __name__ == "__main__":
    main()
