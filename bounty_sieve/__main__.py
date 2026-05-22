"""Command line entrypoint for python -m bounty_sieve."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from bounty_sieve.fixtures import load_fixture_opportunities
from bounty_sieve.io import read_json, write_json, write_text
from bounty_sieve.opportunities import OpportunityValidationError, load_json_opportunities
from bounty_sieve.reporting import render_report
from bounty_sieve.scoring import score_opportunities


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bounty-sieve",
        description="Read-only offline bounty opportunity triage and safety filtering.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Discover opportunities.")
    discover_parser.add_argument("--source", choices=["fixture", "json"], required=True)
    discover_parser.add_argument("--input", help="Path to a user-provided JSON opportunity file.")
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
        if args.source == "fixture":
            if args.input:
                discover_parser.error("--input can only be used with --source json")
            opportunities = load_fixture_opportunities()
        else:
            if not args.input:
                discover_parser.error("--source json requires --input PATH")
            try:
                opportunities = load_json_opportunities(args.input)
            except OpportunityValidationError as exc:
                discover_parser.error(str(exc))
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
        counts = Counter(item["score"]["recommendation"] for item in scored)
        print(f"Wrote offline demo to {out_dir}")
        print(f"- discovered: {discovered_path}")
        print(f"- scored: {scored_path}")
        print(f"- report: {report_path}")
        print(
            "Recommendations: "
            f"pursue={counts.get('pursue', 0)}, "
            f"watch={counts.get('watch', 0)}, "
            f"reject={counts.get('reject', 0)}"
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
