"""Command line entrypoint for python -m bounty_sieve."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from bounty_sieve import __version__
from bounty_sieve.fixtures import load_fixture_opportunities
from bounty_sieve.github_importer import (
    GitHubImportError,
    emit_warnings,
    import_github_issue_url,
    import_url_list,
)
from bounty_sieve.io import read_json, write_json, write_text
from bounty_sieve.opportunities import OpportunityValidationError, load_json_opportunities
from bounty_sieve.reporting import render_report, render_stdout_summary
from bounty_sieve.scoring import score_opportunities


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bounty-sieve",
        description="Offline-by-default read-only bounty opportunity intake, triage, and safety filtering.",
    )
    parser.add_argument(
        "--version", action="version", version=f"bounty-sieve {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a local JSON opportunity file."
    )
    validate_parser.add_argument("input", help="Path to a user-provided JSON opportunity file.")

    discover_parser = subparsers.add_parser("discover", help="Discover opportunities.")
    discover_parser.add_argument(
        "--source",
        choices=["fixture", "json", "github-issue", "url-list"],
        required=True,
        help=(
            "Discovery source. fixture/json are local only; github-issue and url-list "
            "perform explicit read-only public URL fetches."
        ),
    )
    discover_parser.add_argument("--input", help="Path to a user-provided JSON opportunity file.")
    discover_parser.add_argument("--url", help="Public GitHub issue URL for --source github-issue.")
    discover_parser.add_argument("--out", required=True)

    score_parser = subparsers.add_parser("score", help="Score discovered opportunities.")
    score_parser.add_argument("input")
    score_parser.add_argument("--out", required=True)

    report_parser = subparsers.add_parser("report", help="Render a markdown report.")
    report_parser.add_argument("input")
    report_parser.add_argument("--out", required=True)
    report_parser.add_argument(
        "--summary",
        action="store_true",
        help="Print report path, recommendation counts, and summary after writing.",
    )

    demo_parser = subparsers.add_parser("demo", help="Run fixture discovery, scoring, and report.")
    demo_parser.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            opportunities = load_json_opportunities(args.input)
        except OpportunityValidationError as exc:
            validate_parser.error(str(exc))
        ids = ", ".join(item["id"] for item in opportunities) or "(none)"
        noun = "opportunity" if len(opportunities) == 1 else "opportunities"
        print(f"Validated {len(opportunities)} {noun}: {ids}")
        return 0

    if args.command == "discover":
        if args.source == "fixture":
            if args.input:
                discover_parser.error("--input can only be used with --source json or --source url-list")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            opportunities = load_fixture_opportunities()
        elif args.source == "json":
            if not args.input:
                discover_parser.error("--source json requires --input PATH")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            try:
                opportunities = load_json_opportunities(args.input)
            except OpportunityValidationError as exc:
                discover_parser.error(str(exc))
        elif args.source == "github-issue":
            if args.input:
                discover_parser.error("--input cannot be used with --source github-issue")
            if not args.url:
                discover_parser.error("--source github-issue requires --url URL")
            try:
                opportunities = [import_github_issue_url(args.url)]
            except GitHubImportError as exc:
                discover_parser.error(str(exc))
        else:
            if not args.input:
                discover_parser.error("--source url-list requires --input PATH")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            try:
                opportunities, warnings = import_url_list(args.input)
            except OSError as exc:
                discover_parser.error(f"could not read input file {args.input}: {exc}")
            emit_warnings(warnings)
        write_json(args.out, opportunities)
        return 0

    if args.command == "score":
        scored = score_opportunities(read_json(args.input))
        write_json(args.out, scored)
        return 0

    if args.command == "report":
        scored = read_json(args.input)
        report = render_report(scored)
        write_text(args.out, report)
        if args.summary:
            print(render_stdout_summary(scored, args.out))
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
