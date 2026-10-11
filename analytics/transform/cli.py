"""
CLI Interface for Analytics Transformation Pipeline (Roadmap §V1.2)
Usage:
    python -m analytics.transform
    python -m analytics.transform --model stg_customers
    python -m analytics.transform --dry-run
"""

import argparse
import sys
from typing import Any

from analytics.transform.runner import TransformRunner


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run analytics staging transformation pipeline."
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Specify one or more model names to transform (e.g. --model stg_customers).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the topological execution order and dependencies without executing.",
    )
    parser.add_argument(
        "--job-name",
        default="transform",
        help="Custom job identifier for logging to etl.runs (default: transform).",
    )
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    runner = TransformRunner()

    if args.dry_run:
        order = runner.dag.get_execution_order(target_models=args.models)
        print("=== Transformation DAG Execution Plan (Dry Run) ===")
        for idx, m in enumerate(order, start=1):
            deps_str = ", ".join(m.depends_on) if m.depends_on else "None"
            print(f"[{idx}] {m.name} -> {m.full_target_name} (Depends on: {deps_str})")
        sys.exit(0)

    print("Starting transformation pipeline execution...")
    summary: dict[str, Any] = runner.run(models=args.models, job_name=args.job_name)

    print(
        f"\nTransform Run #{summary['run_id']} finished with status: {summary['status'].upper()}"
    )
    print(f"Total Rows Affected: {summary['rows_affected']}")
    print("-" * 75)
    print(f"{'Model':<30} {'Status':<10} {'Rows':<8} {'Time (ms)':<10} {'Checksum'}")
    print("-" * 75)
    for res in summary["models"]:
        model_name = res["model"]
        status = res["status"].upper()
        rows = str(res.get("rows", 0))
        duration = str(res.get("duration_ms", "-"))
        chk = (res.get("checksum") or "")[:12]
        if status == "FAILED":
            err = res.get("error", "")
            print(
                f"{model_name:<30} {status:<10} {rows:<8} {duration:<10} ERROR: {err}"
            )
        elif status == "SKIPPED":
            reason = res.get("error", "")
            print(
                f"{model_name:<30} {status:<10} {rows:<8} {duration:<10} SKIPPED: {reason}"
            )
        else:
            print(f"{model_name:<30} {status:<10} {rows:<8} {duration:<10} {chk}...")

    if summary["status"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
