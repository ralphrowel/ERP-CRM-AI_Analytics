import argparse
import sys
import time
from pathlib import Path

from app.core.database import SessionLocal
from simulator.generator import Simulator
from simulator.legacy_generator import LegacyDataGenerator


def main():
    parser = argparse.ArgumentParser(description="ERP/CRM Business Data Simulator")
    subparsers = parser.add_subparsers(dest="command")

    # Command: run (Operational Simulation)
    run_parser = subparsers.add_parser("run", help="Run operational simulation into database")
    run_parser.add_argument(
        "--months", type=int, default=6, help="Months of history to generate (default: 6)"
    )
    run_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic generation (default: 42)",
    )

    # Command: legacy (Path B Dirty Legacy Export Generator)
    legacy_parser = subparsers.add_parser(
        "legacy", help="Generate dirty legacy CSV exports and defect manifest"
    )
    legacy_parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Random seed for deterministic defect generation (default: 7)",
    )
    legacy_parser.add_argument(
        "--customers",
        type=int,
        default=250,
        help="Number of legacy customer records to generate (default: 250)",
    )
    legacy_parser.add_argument(
        "--sales",
        type=int,
        default=1500,
        help="Number of legacy sales transactions to generate (default: 1500)",
    )
    legacy_parser.add_argument(
        "--out-dir",
        type=str,
        default="data/legacy",
        help="Output directory for legacy CSV files and manifest (default: data/legacy)",
    )

    args = parser.parse_args()

    if args.command == "run" or (args.command is None and len(sys.argv) == 1):
        months = getattr(args, "months", 6)
        seed = getattr(args, "seed", 42)

        print(f"[*] Starting ERP CRM Simulator: {months} months, seed={seed}...")
        start_time = time.time()

        with SessionLocal() as db:
            sim = Simulator(db=db, seed=seed, months=months)
            results = sim.run()

        elapsed = time.time() - start_time
        print(f"[SUCCESS] Simulation complete in {elapsed:.2f}s!")
        print(f"   * Leads created:         {results['leads_created']}")
        print(f"   * Leads converted:       {results['leads_converted']}")
        print(f"   * Opportunities won:     {results['opportunities_won']}")
        print(f"   * Opportunities lost:    {results['opportunities_lost']}")
        print(f"   * Activities recorded:   {results['activities_recorded']}")

    elif args.command == "legacy":
        seed = getattr(args, "seed", 7)
        customers = getattr(args, "customers", 250)
        sales = getattr(args, "sales", 1500)
        out_dir = Path(getattr(args, "out_dir", "data/legacy"))

        print(
            f"[*] Generating dirty legacy data: seed={seed}, customers={customers}, sales={sales}..."
        )
        gen = LegacyDataGenerator(seed=seed, out_dir=out_dir)
        summary = gen.run(customer_count=customers, sales_count=sales)

        print(f"[SUCCESS] Legacy data generation complete in '{out_dir}'!")
        print(f"   * Customers CSV:   {summary['customers_path']}")
        print(f"   * Sales CSV:       {summary['sales_path']}")
        print(f"   * Defect Manifest: {summary['manifest_path']}")
        print(f"   * Total Defects:   {summary['total_defects']}")
        print("   * Defects Breakdown:")
        for k, v in summary["defects_by_type"].items():
            print(f"       - {k}: {v}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
