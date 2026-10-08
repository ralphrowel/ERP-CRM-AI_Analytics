import argparse
import sys
import time

from app.core.database import SessionLocal
from simulator.generator import Simulator


def main():
    parser = argparse.ArgumentParser(description="ERP/CRM Business Data Simulator")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run simulation")
    run_parser.add_argument(
        "--months", type=int, default=6, help="Months of history to generate (default: 6)"
    )
    run_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic generation (default: 42)",
    )

    args = parser.parse_args()

    if args.command == "run" or args.command is None:
        months = getattr(args, "months", 6)
        seed = getattr(args, "seed", 42)

        print(f"🚀 Starting ERP CRM Simulator: {months} months, seed={seed}...")
        start_time = time.time()

        with SessionLocal() as db:
            sim = Simulator(db=db, seed=seed, months=months)
            results = sim.run()

        elapsed = time.time() - start_time
        print(f"✅ Simulation complete in {elapsed:.2f}s!")
        print(f"   • Leads created:         {results['leads_created']}")
        print(f"   • Leads converted:       {results['leads_converted']}")
        print(f"   • Opportunities won:     {results['opportunities_won']}")
        print(f"   • Opportunities lost:    {results['opportunities_lost']}")
        print(f"   • Activities recorded:   {results['activities_recorded']}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
