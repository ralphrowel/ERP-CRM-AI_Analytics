"""
CLI Entrypoint for Data Quality Engine (Roadmap §V1.3)
Supports dataset filtering, dry-run in-memory preview, and mart circuit breaking.
Usage:
    python -m analytics.dq [--dataset legacy_customers] [--preview] [--circuit-breaker]
"""

import argparse
import sys

from analytics.db import get_analytics_engine
from analytics.dq.runner import CircuitBreakerError, DqRunner


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parses command-line arguments for DQ runner."""
    parser = argparse.ArgumentParser(
        description="Visiq Data Quality Engine - Milestone V1.3",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        "-d",
        type=str,
        default=None,
        help="Optional single dataset or comma-separated list of datasets to evaluate (e.g. legacy_customers,legacy_sales)",
    )
    parser.add_argument(
        "--preview",
        "-p",
        action="store_true",
        help="Simulates non-destructive cleaning in memory and outputs projected score improvements without persisting",
    )
    parser.add_argument(
        "--circuit-breaker",
        "-c",
        action="store_true",
        help="Enforces circuit breaker: raises error and blocks mart load if critical severity defects are detected",
    )
    return parser.parse_args(args)


def main(args: list[str] | None = None) -> int:
    """Main CLI execution flow."""
    opts = parse_args(args)
    datasets = [d.strip() for d in opts.dataset.split(",")] if opts.dataset else None

    engine = get_analytics_engine()
    runner = DqRunner(engine)

    try:
        summary = runner.run(
            datasets=datasets,
            preview=opts.preview,
            circuit_breaker=opts.circuit_breaker,
        )

        print("\n=== Visiq Data Quality Engine Completed ===")
        print(f"Status: {summary['status'].upper()}")
        print(f"Run ID: {summary['run_id']}")

        if opts.preview:
            print("\n--- Dry-Run Preview Results ---")
            for ds, prev in summary.get("previews", {}).items():
                print(f"Dataset: {ds}")
                print(
                    f"  Original Score:  {prev.original_score} (Grade {prev.original_grade})"
                )
                print(
                    f"  Projected Score: {prev.projected_score} (Grade {prev.projected_grade})"
                )
                print(f"  Cell Diffs:      {prev.cell_diff_count}")
                print(f"  Coerced Nulls:   {prev.coerced_null_count}")
                print(f"  Quarantined:     {prev.quarantined_count}")
        else:
            print("\n--- Scorecards ---")
            for ds, sc in summary.get("scorecards", {}).items():
                print(f"Dataset: {ds}")
                print(
                    f"  Composite Score: {sc.composite_score} (Grade {sc.letter_grade})"
                )
                print("  Dimension Scores:")
                for dim, score in sc.dimension_scores.items():
                    print(f"    - {dim}: {score}%")
                print(f"  Total Issues:    {sc.total_issues}")
                print(f"  Critical Issues: {sc.critical_failures}")

            if "entity_matches" in summary:
                print(f"\nResolved Entity Matches: {summary['entity_matches']}")
            if summary.get("quarantined_total", 0) > 0:
                print(f"Quarantined Records:     {summary['quarantined_total']}")

        return 0

    except CircuitBreakerError as e:
        print(f"\n[CIRCUIT BREAKER TRIGGERED] {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"\n[ERROR] DQ run failed: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
