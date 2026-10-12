"""
Visiq Analytics CLI (Roadmap §V1.6)
Command-line interface for querying Visiq, running evaluation benchmarks,
and inspecting metric metadata directly from the shell.
"""

import argparse
import json
import sys

from analytics.db import get_analytics_engine
from analytics.visiq.agent import VisiqAgent
from analytics.visiq.catalog import KPI_METRIC_CATALOG
from analytics.visiq.tools import VisiqTools


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m analytics.visiq",
        description="Visiq AI Analytics Assistant CLI (Roadmap §V1.6)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Ask command
    ask_p = subparsers.add_parser("ask", help="Ask an analytical business question")
    ask_p.add_argument("question", type=str, help="Natural language question")
    ask_p.add_argument("--theme", type=str, choices=["light", "dark"], default="light")
    ask_p.add_argument("--json", action="store_true", help="Output raw JSON response")

    # 2. Explain command
    exp_p = subparsers.add_parser("explain", help="Explain a specific KPI metric")
    exp_p.add_argument("kpi_id", type=str, help="KPI ID, e.g. KPI-001")

    # 3. DQ command
    subparsers.add_parser("dq", help="View Data Quality health summary")

    # 4. Catalog command
    subparsers.add_parser("catalog", help="List all 19 conformed KPIs")

    args = parser.parse_args(argv)
    engine = get_analytics_engine()

    if args.command == "ask":
        agent = VisiqAgent(engine)
        res = agent.ask(args.question, theme=args.theme)
        if args.json:
            print(json.dumps(res, indent=2, default=str))
        else:
            print("\n" + "=" * 60)
            print(f"QUESTION: {res['question']}")
            print("=" * 60)
            print(res["narrative"])
            if res.get("freshness"):
                print(
                    f"\nETL Status: {res['freshness'].get('status')} (Completed: {res['freshness'].get('completed_at')})"
                )
            if res.get("dq_warnings"):
                print(f"Active DQ Warnings ({len(res['dq_warnings'])}):")
                for w in res["dq_warnings"]:
                    print(f"  * {w}")
            print("=" * 60 + "\n")
        return 0

    elif args.command == "explain":
        tools = VisiqTools(engine)
        doc = tools.explain_metric(args.kpi_id)
        print(json.dumps(doc, indent=2))
        return 0

    elif args.command == "dq":
        tools = VisiqTools(engine)
        summary = tools.dq_summary()
        print(json.dumps(summary, indent=2))
        return 0

    elif args.command == "catalog":
        print(f"\nVisiq KPI Catalog ({len(KPI_METRIC_CATALOG)} metrics):")
        print("-" * 60)
        for kpi in KPI_METRIC_CATALOG.values():
            print(f"[{kpi.kpi_id}] {kpi.name} ({kpi.category}) - Unit: {kpi.unit}")
        print("-" * 60 + "\n")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
