"""Command line entrypoint for python -m bounty_sieve."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from bounty_sieve import __version__
from bounty_sieve.doctor import format_doctor_result, run_doctor
from bounty_sieve.fixtures import load_fixture_opportunities
from bounty_sieve.github_importer import (
    GitHubImportError,
    emit_warnings,
    import_github_issue_url,
    import_url_list,
)
from bounty_sieve.io import read_json, write_json, write_text
from bounty_sieve.opportunities import OpportunityValidationError, load_json_opportunities
from bounty_sieve.reporting import (
    render_score_stdout_summary,
    render_score_stdout_summary_json,
    render_report,
    render_stdout_summary,
    render_stdout_summary_json,
)
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
    validate_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print machine-readable JSON and no extra prose.",
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
    discover_summary_group = discover_parser.add_mutually_exclusive_group()
    discover_summary_group.add_argument(
        "--summary",
        action="store_true",
        help="Print output path, opportunity count, and IDs after writing.",
    )
    discover_summary_group.add_argument(
        "--summary-json",
        action="store_true",
        help="Print machine-readable discover summary JSON after writing.",
    )

    score_parser = subparsers.add_parser("score", help="Score discovered opportunities.")
    score_parser.add_argument("input")
    score_parser.add_argument(
        "--out",
        help="Write scored JSON to this path. Omit to print compact JSON to stdout.",
    )
    score_summary_group = score_parser.add_mutually_exclusive_group()
    score_summary_group.add_argument(
        "--summary",
        action="store_true",
        help="Print output path, recommendation counts, and summary after writing.",
    )
    score_summary_group.add_argument(
        "--summary-json",
        action="store_true",
        help="Print machine-readable score summary JSON after writing.",
    )

    report_parser = subparsers.add_parser("report", help="Render a markdown report.")
    report_parser.add_argument("input")
    report_parser.add_argument("--out", required=True)
    report_summary_group = report_parser.add_mutually_exclusive_group()
    report_summary_group.add_argument(
        "--summary",
        action="store_true",
        help="Print report path, recommendation counts, and summary after writing.",
    )
    report_summary_group.add_argument(
        "--summary-json",
        action="store_true",
        help="Print machine-readable report summary JSON after writing.",
    )

    demo_parser = subparsers.add_parser("demo", help="Run fixture discovery, scoring, and report.")
    demo_parser.add_argument("--out", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Run local onboarding health checks.")
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print machine-readable JSON and no extra prose.",
    )

    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            opportunities = load_json_opportunities(args.input)
        except OpportunityValidationError as exc:
            if args.json_output:
                payload = {"ok": False, "error": str(exc)}
                print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
                return 2
            validate_parser.error(str(exc))
        ids = ", ".join(item["id"] for item in opportunities) or "(none)"
        if args.json_output:
            payload = {
                "total": len(opportunities),
                "ids": [item["id"] for item in opportunities],
                "ok": True,
            }
            print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            return 0
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
        if args.summary:
            print(_render_discover_summary(opportunities, args.out))
        if args.summary_json:
            print(_render_discover_summary_json(opportunities, args.out))
        return 0

    if args.command == "score":
        if not args.out and (args.summary or args.summary_json):
            score_parser.error(
                "--summary and --summary-json require --out because they summarize a written file"
            )
        try:
            opportunities = load_json_opportunities(args.input)
        except OpportunityValidationError as exc:
            score_parser.error(str(exc))
        scored = score_opportunities(opportunities)
        if not args.out:
            print(json.dumps(scored, separators=(",", ":"), sort_keys=True))
            return 0
        write_json(args.out, scored)
        if args.summary:
            print(render_score_stdout_summary(scored, args.out))
        if args.summary_json:
            print(render_score_stdout_summary_json(scored, args.out))
        return 0

    if args.command == "report":
        if args.out == "-" and (args.summary or args.summary_json):
            report_parser.error(
                "--summary and --summary-json cannot be used with --out - because stdout is reserved for the report"
            )
        try:
            scored = read_json(args.input)
        except FileNotFoundError:
            report_parser.error(f"input file not found: {args.input}")
        except OSError as exc:
            report_parser.error(f"could not read input file {args.input}: {exc}")
        except ValueError as exc:
            report_parser.error(f"input file is not valid JSON: {exc}")
        report = render_report(scored)
        if args.out == "-":
            print(report, end="")
            return 0
        write_text(args.out, report)
        if args.summary:
            print(render_stdout_summary(scored, args.out))
        if args.summary_json:
            print(render_stdout_summary_json(scored, args.out))
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

    if args.command == "doctor":
        result = run_doctor()
        if args.json_output:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(format_doctor_result(result))
        return 0 if result["ok"] else 1

    parser.error(f"unknown command: {args.command}")
    return 2


def _render_discover_summary(opportunities: list[dict], output_path: str | Path) -> str:
    ids = [item["id"] for item in opportunities]
    return "\n".join(
        [
            f"Output: {output_path}",
            f"Total: {len(opportunities)}",
            f"IDs: {', '.join(ids) or '(none)'}",
        ]
    )


def _render_discover_summary_json(opportunities: list[dict], output_path: str | Path) -> str:
    payload = {
        "ok": True,
        "output": str(output_path),
        "total": len(opportunities),
        "ids": [item["id"] for item in opportunities],
    }
    return json.dumps(payload, separators=(",", ":"))


if __name__ == "__main__":
    raise SystemExit(main())
