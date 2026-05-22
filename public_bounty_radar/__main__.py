"""Command line entrypoint for python -m public_bounty_radar."""

from __future__ import annotations

import argparse
from pathlib import Path

from public_bounty_radar.fixtures import load_fixture_opportunities
from public_bounty_radar.io import read_json, write_json, write_text
from public_bounty_radar.reporting import render_report
from public_bounty_radar.scoring import score_opportunities


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="public_bounty_radar",
        description="Read-only offline public bounty discovery and risk triage.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Discover opportunities.")
    discover_parser.add_argument("--source", choices=["fixture"], required=True)
    discover_parser.add_argument("--out", required=True)

    score_parser = subparsers.add_parser("score", help="Score discovered opportunities.")
    score_parser.add_argument("input")
    score_parser.add_argument("--out", required=True)

    report_parser = subparsers.add_parser("report", help="Render a markdown report.")
    report_parser.add_argument("input")
    report_parser.add_argument("--out", required=True)

    demo_parser = subparsers.add_parser("demo", help="Run fixture discovery, scoring, and report.")
    demo_parser.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    if args.command == "discover":
        opportunities = load_fixture_opportunities()
        write_json(args.out, opportunities)
        return 0

    if args.command == "score":
        scored = score_opportunities(read_json(args.input))
        write_json(args.out, scored)
        return 0

    if args.command == "report":
        report = render_report(read_json(args.input))
        write_text(args.out, report)
        return 0

    if args.command == "demo":
        out_dir = Path(args.out)
        discovered_path = out_dir / "discovered.json"
        scored_path = out_dir / "scored.json"
        report_path = out_dir / "report.md"
        opportunities = load_fixture_opportunities()
        scored = score_opportunities(opportunities)
        write_json(discovered_path, opportunities)
        write_json(scored_path, scored)
        write_text(report_path, render_report(scored))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
