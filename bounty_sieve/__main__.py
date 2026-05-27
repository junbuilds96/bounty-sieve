"""Command line entrypoint for python -m bounty_sieve."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from bounty_sieve import __version__
from bounty_sieve.bounty_targets_importer import (
    BountyTargetsDataImportError,
    import_bounty_targets_data,
)
from bounty_sieve.doctor import format_doctor_result, run_doctor
from bounty_sieve.fixtures import load_fixture_opportunities
from bounty_sieve.github_importer import (
    GitHubImportError,
    emit_warnings,
    import_github_search,
    import_github_issue_url,
    import_url_list,
)
from bounty_sieve.io import read_json, write_json, write_text
from bounty_sieve.opportunities import (
    OpportunityValidationError,
    load_json_opportunities,
    normalize_opportunities,
)
from bounty_sieve.reporting import (
    render_html_report,
    render_score_stdout_summary,
    render_score_stdout_summary_json,
    render_report,
    render_stdout_summary,
    render_stdout_summary_json,
)
from bounty_sieve.scoring import score_opportunities


class DiscoverHelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog: str) -> None:
        super().__init__(prog, width=100)


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

    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover opportunities.",
        formatter_class=DiscoverHelpFormatter,
    )
    discover_parser.add_argument(
        "--source",
        choices=[
            "fixture",
            "json",
            "bounty-targets-data",
            "github-issue",
            "github-search",
            "url-list",
        ],
        required=True,
        help=(
            "Discovery source. fixture/json/bounty-targets-data are local only; "
            "github-issue, github-search, and url-list perform explicit read-only public fetches."
        ),
    )
    discover_parser.add_argument("--input", help="Path to a user-provided JSON opportunity file.")
    discover_parser.add_argument(
        "--platform",
        choices=["hackerone", "bugcrowd"],
        help="Bounty platform for --source bounty-targets-data.",
    )
    discover_parser.add_argument("--url", help="Public GitHub issue URL for --source github-issue.")
    discover_parser.add_argument("--query", help="GitHub issue search query for --source github-search.")
    discover_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum GitHub search results for --source github-search; default 10, max 50.",
    )
    discover_parser.add_argument(
        "--repo-health",
        action="store_true",
        help=(
            "For --source github-search, fetch read-only public repository metadata "
            "and include compact health signals."
        ),
    )
    discover_parser.add_argument("--out")
    discover_parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Preview bounty-targets-data, github-issue, github-search, or url-list imports "
            "as compact JSON without requiring --out or writing files."
        ),
    )
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

    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare two local opportunity JSON files after scoring.",
        description="Compare two local opportunity JSON files after normalizing and scoring.",
    )
    compare_parser.add_argument("before", help="Earlier local opportunity JSON file.")
    compare_parser.add_argument("after", help="Later local opportunity JSON file.")
    compare_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print machine-readable JSON and no markdown.",
    )
    compare_parser.add_argument(
        "--out",
        help="Write the compare report to this path instead of stdout.",
    )

    rank_parser = subparsers.add_parser(
        "rank", help="Print a ranked terminal view of discovered opportunities."
    )
    rank_parser.add_argument("input")
    rank_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum ranked opportunities to show; default all.",
    )
    rank_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print machine-readable JSON and no table.",
    )

    search_preview_parser = subparsers.add_parser(
        "search-preview",
        help="Preview ranked public GitHub issues from a read-only search.",
        description="Preview ranked public GitHub issues from a read-only search.",
    )
    search_preview_parser.add_argument(
        "--query",
        required=True,
        help="GitHub issue search query.",
    )
    search_preview_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum GitHub search results to import and preview; default 10, max 50.",
    )
    search_preview_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print compact machine-readable JSON and no markdown.",
    )
    search_preview_parser.add_argument(
        "--repo-health",
        action="store_true",
        help=(
            "Fetch read-only public repository metadata and include compact health "
            "signals in the preview."
        ),
    )

    search_report_parser = subparsers.add_parser(
        "search-report",
        help="Search public GitHub issues, score them, and write a decision brief.",
        description="Search public GitHub issues, score them, and write a decision brief.",
    )
    search_report_parser.add_argument(
        "--query",
        required=True,
        help="GitHub issue search query.",
    )
    search_report_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum GitHub search results to import and report; default 10, max 50.",
    )
    search_report_parser.add_argument(
        "--out",
        required=True,
        help="Write Markdown decision brief to this path.",
    )
    search_report_parser.add_argument(
        "--json-out",
        help="Optional path for the scored JSON opportunities used for the report.",
    )
    search_report_parser.add_argument(
        "--repo-health",
        action="store_true",
        help=(
            "Fetch read-only public repository metadata and include compact health "
            "signals before scoring."
        ),
    )
    search_report_summary_group = search_report_parser.add_mutually_exclusive_group()
    search_report_summary_group.add_argument(
        "--summary",
        action="store_true",
        help="Print report path, recommendation counts, and summary after writing.",
    )
    search_report_summary_group.add_argument(
        "--summary-json",
        action="store_true",
        help="Print machine-readable report summary JSON after writing.",
    )

    shortlist_parser = subparsers.add_parser(
        "shortlist",
        help="Export a local read-only shortlist for review or agent handoff.",
        description="Export a local read-only shortlist for review or agent handoff.",
    )
    shortlist_parser.add_argument("input")
    shortlist_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum selected opportunities to export; default 3.",
    )
    shortlist_parser.add_argument(
        "--recommendation",
        action="append",
        help=(
            "Recommendation to include. May be repeated or comma-separated; "
            "choices: pursue, watch, reject. Default: pursue."
        ),
    )
    shortlist_parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format; default markdown.",
    )
    shortlist_parser.add_argument(
        "--out",
        required=True,
        help="Output path, or - for stdout.",
    )

    next_parser = subparsers.add_parser(
        "next", help="Print the single best next opportunity."
    )
    next_parser.add_argument("input")
    next_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print machine-readable JSON and no extra prose.",
    )

    explain_parser = subparsers.add_parser(
        "explain",
        help="Print a read-only decision card for one opportunity.",
        description="Print a read-only decision card for one opportunity.",
    )
    explain_parser.add_argument("input")
    explain_parser.add_argument("opportunity_id", help="Opportunity id to explain.")
    explain_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print machine-readable JSON and no extra prose.",
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
    demo_parser.add_argument(
        "--html",
        action="store_true",
        help="Also write report.html for a local offline visual report.",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Run local onboarding health checks.")
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print machine-readable JSON and no extra prose.",
    )
    doctor_parser.add_argument(
        "--example",
        metavar="PATH",
        help="Path to a user-provided JSON opportunity file for the minimal_example check.",
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
        if args.dry_run and args.source not in {
            "bounty-targets-data",
            "github-issue",
            "github-search",
            "url-list",
        }:
            discover_parser.error(
                "--dry-run can only be used with --source bounty-targets-data, --source github-issue, --source github-search, or --source url-list"
            )
        if args.dry_run and (args.summary or args.summary_json):
            discover_parser.error("--summary and --summary-json cannot be used with --dry-run")
        if not args.dry_run and not args.out:
            discover_parser.error("the following arguments are required: --out")
        if args.source == "fixture":
            if args.input:
                discover_parser.error(
                    "--input can only be used with --source json, --source bounty-targets-data, or --source url-list"
                )
            if args.platform:
                discover_parser.error("--platform can only be used with --source bounty-targets-data")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
            if args.repo_health:
                discover_parser.error("--repo-health can only be used with --source github-search")
            opportunities = load_fixture_opportunities()
        elif args.source == "json":
            if not args.input:
                discover_parser.error("--source json requires --input PATH")
            if args.platform:
                discover_parser.error("--platform can only be used with --source bounty-targets-data")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
            if args.repo_health:
                discover_parser.error("--repo-health can only be used with --source github-search")
            try:
                opportunities = load_json_opportunities(args.input)
            except OpportunityValidationError as exc:
                discover_parser.error(str(exc))
        elif args.source == "bounty-targets-data":
            if not args.input:
                discover_parser.error("--source bounty-targets-data requires --input PATH")
            if not args.platform:
                discover_parser.error("--source bounty-targets-data requires --platform hackerone|bugcrowd")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
            if args.repo_health:
                discover_parser.error("--repo-health can only be used with --source github-search")
            try:
                opportunities = import_bounty_targets_data(args.input, args.platform)
            except BountyTargetsDataImportError as exc:
                discover_parser.error(str(exc))
            if args.dry_run:
                print(json.dumps(opportunities, separators=(",", ":"), sort_keys=True))
                return 0
        elif args.source == "github-issue":
            if args.input:
                discover_parser.error("--input cannot be used with --source github-issue")
            if args.platform:
                discover_parser.error("--platform can only be used with --source bounty-targets-data")
            if not args.url:
                discover_parser.error("--source github-issue requires --url URL")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
            if args.repo_health:
                discover_parser.error("--repo-health can only be used with --source github-search")
            try:
                opportunities = normalize_opportunities([import_github_issue_url(args.url)])
            except (GitHubImportError, OpportunityValidationError) as exc:
                discover_parser.error(str(exc))
            if args.dry_run:
                print(json.dumps(opportunities, separators=(",", ":"), sort_keys=True))
                return 0
        elif args.source == "github-search":
            if args.input:
                discover_parser.error("--input cannot be used with --source github-search")
            if args.platform:
                discover_parser.error("--platform can only be used with --source bounty-targets-data")
            if args.url:
                discover_parser.error("--url cannot be used with --source github-search")
            if not args.query:
                discover_parser.error("--source github-search requires --query QUERY")
            limit = 10 if args.limit is None else args.limit
            if limit < 1 or limit > 50:
                discover_parser.error("--limit must be between 1 and 50")
            try:
                if args.repo_health:
                    imported = import_github_search(args.query, limit, include_repo_health=True)
                else:
                    imported = import_github_search(args.query, limit)
                opportunities = normalize_opportunities(imported)
            except (GitHubImportError, OpportunityValidationError) as exc:
                discover_parser.error(str(exc))
            if args.dry_run:
                print(json.dumps(opportunities, separators=(",", ":"), sort_keys=True))
                return 0
        else:
            if not args.input:
                discover_parser.error("--source url-list requires --input PATH")
            if args.platform:
                discover_parser.error("--platform can only be used with --source bounty-targets-data")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
            if args.repo_health:
                discover_parser.error("--repo-health can only be used with --source github-search")
            try:
                opportunities, warnings = import_url_list(args.input)
            except OSError as exc:
                discover_parser.error(f"could not read input file {args.input}: {exc}")
            emit_warnings(warnings)
            if args.dry_run:
                try:
                    opportunities = normalize_opportunities(opportunities)
                except OpportunityValidationError as exc:
                    discover_parser.error(str(exc))
                print(json.dumps(opportunities, separators=(",", ":"), sort_keys=True))
                return 0
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

    if args.command == "compare":
        try:
            before = score_opportunities(load_json_opportunities(args.before))
        except OpportunityValidationError as exc:
            compare_parser.error(f"before input: {exc}")
        try:
            after = score_opportunities(load_json_opportunities(args.after))
        except OpportunityValidationError as exc:
            compare_parser.error(f"after input: {exc}")
        comparison = _compare_scored_opportunities(before, after)
        if args.json_output:
            payload = _compare_json_payload(before, after, comparison)
            if args.out:
                write_json(args.out, payload)
            else:
                print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            return 0
        markdown = _render_compare_markdown(before, after, comparison)
        if args.out:
            write_text(args.out, markdown)
        else:
            print(markdown, end="")
        return 0

    if args.command == "rank":
        if args.limit is not None and args.limit <= 0:
            rank_parser.error("--limit must be greater than 0")
        try:
            opportunities = load_json_opportunities(args.input)
        except OpportunityValidationError as exc:
            rank_parser.error(str(exc))
        scored = score_opportunities(opportunities)
        ranked = _rank_scored_opportunities(scored)
        shown = ranked if args.limit is None else ranked[: args.limit]
        if args.json_output:
            print(_render_rank_json(ranked, shown))
        else:
            print(_render_rank_table(shown))
        return 0

    if args.command == "search-preview":
        if args.limit < 1 or args.limit > 50:
            search_preview_parser.error("--limit must be between 1 and 50")
        try:
            if args.repo_health:
                imported = import_github_search(
                    args.query,
                    args.limit,
                    include_repo_health=True,
                )
            else:
                imported = import_github_search(args.query, args.limit)
            opportunities = normalize_opportunities(imported)
        except (GitHubImportError, OpportunityValidationError) as exc:
            search_preview_parser.error(str(exc))
        ranked = _rank_scored_opportunities(score_opportunities(opportunities))
        if args.json_output:
            print(_render_search_preview_json(args.query, ranked))
        else:
            print(_render_search_preview_markdown(args.query, args.limit, ranked))
        return 0

    if args.command == "search-report":
        if args.limit < 1 or args.limit > 50:
            search_report_parser.error("--limit must be between 1 and 50")
        try:
            if args.repo_health:
                imported = import_github_search(
                    args.query,
                    args.limit,
                    include_repo_health=True,
                )
            else:
                imported = import_github_search(args.query, args.limit)
            opportunities = normalize_opportunities(imported)
        except (GitHubImportError, OpportunityValidationError) as exc:
            search_report_parser.error(str(exc))
        scored = score_opportunities(opportunities)
        write_text(args.out, render_report(scored))
        if args.json_out:
            write_json(args.json_out, scored)
        if args.summary:
            print(render_stdout_summary(scored, args.out))
        if args.summary_json:
            print(render_stdout_summary_json(scored, args.out))
        return 0

    if args.command == "shortlist":
        if args.limit <= 0:
            shortlist_parser.error("--limit must be greater than 0")
        recommendations = _parse_shortlist_recommendations(args.recommendation)
        if not recommendations:
            shortlist_parser.error("--recommendation must include at least one value")
        invalid_recommendations = [
            recommendation
            for recommendation in recommendations
            if recommendation not in RECOMMENDATION_VALUES
        ]
        if invalid_recommendations:
            allowed = ", ".join(RECOMMENDATION_VALUES)
            invalid = ", ".join(invalid_recommendations)
            shortlist_parser.error(f"--recommendation must be one of: {allowed}; got: {invalid}")
        try:
            opportunities = load_json_opportunities(args.input)
        except OpportunityValidationError as exc:
            shortlist_parser.error(str(exc))
        ranked = _rank_scored_opportunities(score_opportunities(opportunities))
        selected = [
            item
            for item in ranked
            if item.get("score", {}).get("recommendation") in set(recommendations)
        ][: args.limit]
        if args.format == "json":
            payload = _shortlist_json_payload(ranked, selected)
            if args.out == "-":
                print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            else:
                write_json(args.out, payload)
        else:
            markdown = _render_shortlist_markdown(ranked, selected, recommendations, args.limit)
            if args.out == "-":
                print(markdown, end="")
            else:
                write_text(args.out, markdown)
        return 0

    if args.command == "next":
        try:
            opportunities = load_json_opportunities(args.input)
        except OpportunityValidationError as exc:
            next_parser.error(str(exc))
        ranked = _rank_scored_opportunities(score_opportunities(opportunities))
        selected = ranked[0] if ranked else None
        if args.json_output:
            print(_render_next_json(len(ranked), selected))
        else:
            print(_render_next_human(selected))
        return 0

    if args.command == "explain":
        try:
            opportunities = load_json_opportunities(args.input)
        except OpportunityValidationError as exc:
            explain_parser.error(str(exc))
        scored = score_opportunities(opportunities)
        selected = _find_scored_opportunity(scored, args.opportunity_id)
        if selected is None:
            available_ids = [item["id"] for item in scored]
            if args.json_output:
                print(_render_explain_not_found_json(args.opportunity_id, available_ids))
            else:
                print(
                    _explain_not_found_message(args.opportunity_id, available_ids),
                    file=sys.stderr,
                )
            return 1
        if args.json_output:
            print(_render_explain_json(len(scored), selected))
        else:
            print(_render_explain_human(selected))
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
        html_report_path = out_dir / "report.html"
        opportunities = load_fixture_opportunities()
        scored = score_opportunities(opportunities)
        write_json(discovered_path, opportunities)
        write_json(scored_path, scored)
        write_text(report_path, render_report(scored))
        if args.html:
            write_text(html_report_path, render_html_report(scored))
        counts = Counter(item["score"]["recommendation"] for item in scored)
        print(f"Wrote offline demo to {out_dir}")
        print(f"- discovered: {discovered_path}")
        print(f"- scored: {scored_path}")
        print(f"- report: {report_path}")
        if args.html:
            print(f"- html: {html_report_path}")
        print(
            "Recommendations: "
            f"pursue={counts.get('pursue', 0)}, "
            f"watch={counts.get('watch', 0)}, "
            f"reject={counts.get('reject', 0)}"
        )
        return 0

    if args.command == "doctor":
        result = run_doctor(example_path=args.example)
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


def _compare_scored_opportunities(before: list[dict], after: list[dict]) -> dict:
    before_by_id = {item["id"]: item for item in before}
    after_by_id = {item["id"]: item for item in after}
    before_ids = set(before_by_id)
    after_ids = set(after_by_id)
    common_ids = before_ids.intersection(after_ids)

    changed_recommendation = [
        opportunity_id
        for opportunity_id in common_ids
        if _score_recommendation(before_by_id[opportunity_id])
        != _score_recommendation(after_by_id[opportunity_id])
    ]
    changed_roi_score = [
        opportunity_id
        for opportunity_id in common_ids
        if _score_roi(before_by_id[opportunity_id]) != _score_roi(after_by_id[opportunity_id])
    ]
    changed_recommendation_ids = set(changed_recommendation)
    changed_roi_score_ids = set(changed_roi_score)
    unchanged = [
        opportunity_id
        for opportunity_id in common_ids
        if opportunity_id not in changed_recommendation_ids
        and opportunity_id not in changed_roi_score_ids
    ]

    return {
        "added": sorted(after_ids - before_ids),
        "removed": sorted(before_ids - after_ids),
        "changed_recommendation": sorted(changed_recommendation),
        "changed_roi_score": sorted(changed_roi_score),
        "unchanged": sorted(unchanged),
        "before_by_id": before_by_id,
        "after_by_id": after_by_id,
    }


def _compare_json_payload(before: list[dict], after: list[dict], comparison: dict) -> dict:
    return {
        "ok": True,
        "before_total": len(before),
        "after_total": len(after),
        "counts": _compare_counts(comparison),
        "added": [
            _compare_item_payload(comparison["after_by_id"][opportunity_id])
            for opportunity_id in comparison["added"]
        ],
        "removed": [
            _compare_item_payload(comparison["before_by_id"][opportunity_id])
            for opportunity_id in comparison["removed"]
        ],
        "changed_recommendation": [
            _compare_change_payload(opportunity_id, comparison)
            for opportunity_id in comparison["changed_recommendation"]
        ],
        "changed_roi_score": [
            _compare_change_payload(opportunity_id, comparison)
            for opportunity_id in comparison["changed_roi_score"]
        ],
        "safety_boundary": _compare_safety_boundary_text(),
    }


def _compare_counts(comparison: dict) -> dict[str, int]:
    return {
        "added": len(comparison["added"]),
        "removed": len(comparison["removed"]),
        "changed_recommendation": len(comparison["changed_recommendation"]),
        "changed_roi_score": len(comparison["changed_roi_score"]),
        "unchanged": len(comparison["unchanged"]),
    }


def _compare_item_payload(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "recommendation": _score_recommendation(item),
        "roi_score": _score_roi(item),
    }


def _compare_change_payload(opportunity_id: str, comparison: dict) -> dict:
    before = comparison["before_by_id"][opportunity_id]
    after = comparison["after_by_id"][opportunity_id]
    return {
        "id": opportunity_id,
        "before": {
            "recommendation": _score_recommendation(before),
            "roi_score": _score_roi(before),
        },
        "after": {
            "recommendation": _score_recommendation(after),
            "roi_score": _score_roi(after),
        },
    }


def _render_compare_markdown(before: list[dict], after: list[dict], comparison: dict) -> str:
    counts = _compare_counts(comparison)
    lines = [
        "# Bounty Sieve Compare",
        "",
        "## Safety Boundary",
        "",
        _compare_safety_boundary_text(),
        "",
        "## Counts",
        "",
        f"- Before total: {len(before)}",
        f"- After total: {len(after)}",
        f"- Added: {counts['added']}",
        f"- Removed: {counts['removed']}",
        f"- Changed recommendation: {counts['changed_recommendation']}",
        f"- Changed ROI score: {counts['changed_roi_score']}",
        f"- Unchanged: {counts['unchanged']}",
        "",
        "## Added",
        "",
    ]
    _extend_compare_item_lines(lines, comparison, "added", "after_by_id")
    lines.extend(["## Removed", ""])
    _extend_compare_item_lines(lines, comparison, "removed", "before_by_id")
    lines.extend(["## Changed Recommendation", ""])
    _extend_compare_change_lines(lines, comparison, "changed_recommendation")
    lines.extend(["## Changed ROI Score", ""])
    _extend_compare_change_lines(lines, comparison, "changed_roi_score")
    return "\n".join(lines)


def _extend_compare_item_lines(
    lines: list[str], comparison: dict, id_key: str, item_map_key: str
) -> None:
    opportunity_ids = comparison[id_key]
    if not opportunity_ids:
        lines.extend(["No items.", ""])
        return
    for opportunity_id in opportunity_ids:
        item = comparison[item_map_key][opportunity_id]
        lines.append(
            f"- {opportunity_id}: recommendation={_score_recommendation(item)}, "
            f"roi_score={_score_roi(item)}"
        )
    lines.append("")


def _extend_compare_change_lines(lines: list[str], comparison: dict, id_key: str) -> None:
    opportunity_ids = comparison[id_key]
    if not opportunity_ids:
        lines.extend(["No changes.", ""])
        return
    for opportunity_id in opportunity_ids:
        before = comparison["before_by_id"][opportunity_id]
        after = comparison["after_by_id"][opportunity_id]
        lines.append(
            f"- {opportunity_id}: recommendation "
            f"{_score_recommendation(before)} -> {_score_recommendation(after)}, "
            f"roi_score {_score_roi(before)} -> {_score_roi(after)}"
        )
    lines.append("")


def _score_recommendation(item: dict) -> object:
    return item.get("score", {}).get("recommendation")


def _score_roi(item: dict) -> object:
    return item.get("score", {}).get("roi_score")


def _compare_safety_boundary_text() -> str:
    return (
        "This compare is local and read-only: it normalizes and scores the provided JSON files "
        "only, performs no network access, requests no credentials, writes only when --out is "
        "provided, and reports only opportunity IDs plus recommendation and ROI changes."
    )


def _rank_scored_opportunities(scored: list[dict]) -> list[dict]:
    recommendation_priority = {"pursue": 0, "watch": 1, "reject": 2}

    def sort_key(indexed_item: tuple[int, dict]) -> tuple[int, int, int]:
        index, item = indexed_item
        score = item.get("score", {})
        recommendation = score.get("recommendation")
        priority = recommendation_priority.get(recommendation, 99)
        roi_score = score.get("roi_score", 0)
        roi = roi_score if isinstance(roi_score, int | float) else 0
        return priority, -int(roi), index

    return [item for _, item in sorted(enumerate(scored), key=sort_key)]


RECOMMENDATION_VALUES = ("pursue", "watch", "reject")


def _parse_shortlist_recommendations(values: list[str] | None) -> list[str]:
    if not values:
        return ["pursue"]
    recommendations: list[str] = []
    for value in values:
        recommendations.extend(
            recommendation.strip() for recommendation in value.split(",") if recommendation.strip()
        )
    return recommendations


def _shortlist_json_payload(ranked: list[dict], selected: list[dict]) -> dict:
    return {
        "ok": True,
        "total": len(ranked),
        "selected": len(selected),
        "items": [_rank_item_payload(item) for item in selected],
        "manual_verification_checklist": _manual_verification_checklist(),
        "safety_boundary": _shortlist_safety_boundary_text(),
    }


def _render_shortlist_markdown(
    ranked: list[dict], selected: list[dict], recommendations: list[str], limit: int
) -> str:
    lines = [
        "# Bounty Sieve Shortlist",
        "",
        "## Safety Boundary",
        "",
        _shortlist_safety_boundary_text(),
        "",
        "## Selection",
        "",
        f"- Selected: {len(selected)} of {len(ranked)} total opportunities",
        f"- Recommendation filter: {', '.join(recommendations)}",
        f"- Limit: {limit}",
        "",
        "## Items",
        "",
    ]
    if selected:
        for index, item in enumerate(selected, start=1):
            score = item.get("score", {})
            lines.extend(
                [
                    f"### {index}. {item.get('title', '')}",
                    "",
                    f"- ID: {item.get('id', '')}",
                    f"- URL: {item.get('url') or 'not provided'}",
                    f"- Recommendation: {score.get('recommendation', '')}",
                    f"- ROI: {score.get('roi_score', 0)}",
                    f"- Reward: {_format_rank_reward(score.get('reward_estimate_usd', 0))}",
                    "- Reasons:",
                ]
            )
            reasons = score.get("reasons", [])
            if reasons:
                lines.extend(f"  - {reason}" for reason in reasons)
            else:
                lines.append("  - No specific reason recorded.")
            lines.append("")
    else:
        lines.extend(["No opportunities matched the recommendation filter.", ""])

    lines.extend(
        [
            "## Manual Verification Checklist",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _manual_verification_checklist())
    lines.extend(
        [
            "",
            "## Agent Handoff",
            "",
            "This file is only a local review shortlist. It is not approval to clone, comment, claim work, submit PRs, log in, use credentials, connect wallets, star repositories, or contact maintainers.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_rank_json(ranked: list[dict], shown: list[dict]) -> str:
    payload = {
        "ok": True,
        "total": len(ranked),
        "shown": len(shown),
        "items": [_rank_item_payload(item) for item in shown],
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _render_search_preview_json(query: str, ranked: list[dict]) -> str:
    payload = {
        "ok": True,
        "query": query,
        "total": len(ranked),
        "ranked": [_search_preview_item_payload(item) for item in ranked],
        "safety_boundary": _search_preview_safety_boundary_text(),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _render_search_preview_markdown(query: str, limit: int, ranked: list[dict]) -> str:
    lines = [
        "# Bounty Sieve Search Preview",
        "",
        "## Safety Boundary",
        "",
        _search_preview_safety_boundary_text(),
        "",
        "## Search",
        "",
        f"- Query: {query}",
        f"- Limit: {limit}",
        f"- Imported and scored: {len(ranked)}",
        "",
        "## Ranked Opportunities",
        "",
    ]
    if ranked:
        for index, item in enumerate(ranked, start=1):
            score = item.get("score", {})
            item_lines = [
                f"### {index}. {item.get('title', '')}",
                "",
                f"- ID: {item.get('id', '')}",
                f"- Recommendation: {score.get('recommendation', '')}",
                f"- ROI: {score.get('roi_score', 0)}",
                f"- Repository: {item.get('repo') or 'not provided'}",
                f"- URL: {item.get('url') or 'not provided'}",
            ]
            repo_health = _repo_health_payload(item)
            if repo_health:
                item_lines.append(f"- Repo health: {_format_repo_health(repo_health)}")
            item_lines.append("")
            lines.extend(item_lines)
    else:
        lines.extend(["No public GitHub issues matched the query after import filtering.", ""])

    lines.extend(
        [
            "## Manual Approval Boundary",
            "",
            (
                "Review the public issue manually before acting. This preview is not approval "
                "to clone, claim work, comment, open PRs, log in, use credentials, touch "
                "wallets, star repositories, or contact maintainers."
            ),
        ]
    )
    return "\n".join(lines)


def _search_preview_item_payload(item: dict) -> dict:
    payload = _rank_item_payload(item)
    payload["repo"] = item.get("repo")
    repo_health = _repo_health_payload(item)
    if repo_health:
        payload["repo_health"] = repo_health
    return payload


def _repo_health_payload(item: dict) -> dict | None:
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        return None
    github_metadata = metadata.get("github")
    if not isinstance(github_metadata, dict):
        return None
    repo_health = github_metadata.get("repo_health")
    if not isinstance(repo_health, dict):
        return None
    keys = [
        "stars",
        "open_issues_count",
        "archived",
        "pushed_at",
        "updated_at",
        "repo_activity",
        "reason",
    ]
    return {key: repo_health.get(key) for key in keys if key in repo_health}


def _format_repo_health(repo_health: dict) -> str:
    parts = [
        f"activity={repo_health.get('repo_activity', 'unknown')}",
        f"archived={_format_bool(repo_health.get('archived'))}",
    ]
    if repo_health.get("stars") is not None:
        parts.append(f"stars={repo_health['stars']}")
    if repo_health.get("open_issues_count") is not None:
        parts.append(f"open_issues={repo_health['open_issues_count']}")
    if repo_health.get("pushed_at"):
        parts.append(f"pushed_at={repo_health['pushed_at']}")
    elif repo_health.get("updated_at"):
        parts.append(f"updated_at={repo_health['updated_at']}")
    if repo_health.get("reason"):
        parts.append(f"reason={repo_health['reason']}")
    return ", ".join(parts)


def _format_bool(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "unknown"


def _rank_item_payload(item: dict) -> dict:
    score = item.get("score", {})
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "url": item.get("url"),
        "recommendation": score.get("recommendation"),
        "roi_score": score.get("roi_score"),
        "reward_estimate_usd": score.get("reward_estimate_usd"),
        "reasons": score.get("reasons", []),
    }


def _render_next_json(total: int, selected: dict | None) -> str:
    payload = {
        "ok": True,
        "total": total,
        "item": _rank_item_payload(selected) if selected else None,
    }
    if selected is None:
        payload["message"] = _next_empty_message()
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _render_next_human(selected: dict | None) -> str:
    if selected is None:
        return _next_empty_message()

    score = selected.get("score", {})
    lines = [
        f"Next opportunity: {selected.get('title', '')}",
        f"ID: {selected.get('id', '')}",
        f"Recommendation: {score.get('recommendation', '')}",
        f"ROI: {score.get('roi_score', 0)}",
        f"Reward: {_format_rank_reward(score.get('reward_estimate_usd', 0))}",
    ]
    if selected.get("url"):
        lines.append(f"URL: {selected['url']}")
    reasons = score.get("reasons", [])
    if reasons:
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in reasons)
    return "\n".join(lines)


def _next_empty_message() -> str:
    return "No opportunities found. Add opportunities first, then rerun next."


def _find_scored_opportunity(scored: list[dict], opportunity_id: str) -> dict | None:
    return next((item for item in scored if item.get("id") == opportunity_id), None)


def _render_explain_json(total: int, selected: dict) -> str:
    payload = {
        "ok": True,
        "total": total,
        "item": _explain_item_payload(selected),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _render_explain_not_found_json(opportunity_id: str, available_ids: list[str]) -> str:
    payload = {
        "ok": False,
        "error": f"opportunity id not found: {opportunity_id}",
        "id": opportunity_id,
        "available_ids": available_ids,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _explain_item_payload(item: dict) -> dict:
    score = item.get("score", {})
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "url": item.get("url"),
        "recommendation": score.get("recommendation"),
        "roi_score": score.get("roi_score"),
        "reward_estimate_usd": score.get("reward_estimate_usd"),
        "score_components": _score_component_payload(score),
        "reasons": score.get("reasons", []),
        "manual_verification_checklist": _manual_verification_checklist(),
        "safety_boundary": _safety_boundary_text(),
    }


def _score_component_payload(score: dict) -> dict:
    keys = [
        "payment_confidence",
        "issue_clarity",
        "repo_activity",
        "competition_risk",
        "complexity_estimate",
        "tech_match",
        "scope_risk",
    ]
    return {key: score.get(key) for key in keys}


def _render_explain_human(selected: dict) -> str:
    score = selected.get("score", {})
    lines = [
        f"Decision card: {selected.get('title', '')}",
        f"ID: {selected.get('id', '')}",
        f"Recommendation: {score.get('recommendation', '')}",
        f"ROI: {score.get('roi_score', 0)}",
        f"Reward: {_format_rank_reward(score.get('reward_estimate_usd', 0))}",
    ]
    if selected.get("url"):
        lines.append(f"Public URL: {selected['url']}")

    lines.append("Score components:")
    components = _score_component_payload(score)
    lines.extend(f"- {key}: {value}" for key, value in components.items())

    lines.append("Reasons:")
    reasons = score.get("reasons", [])
    if reasons:
        lines.extend(f"- {reason}" for reason in reasons)
    else:
        lines.append("- No specific reason recorded.")

    lines.append("Manual verification checklist:")
    lines.extend(f"- {item}" for item in _manual_verification_checklist())
    lines.append("Safety boundary:")
    lines.append(f"- {_safety_boundary_text()}")
    return "\n".join(lines)


def _manual_verification_checklist() -> list[str]:
    return [
        "Confirm the opportunity is still open and not already claimed or solved.",
        "Confirm payment terms, scope, acceptance criteria, and maintainer or poster activity.",
        "Confirm the task does not require credentials, secrets, wallet access, unknown assets, private data, prompt extraction, engagement farming, or duplicate low-value PRs.",
    ]


def _safety_boundary_text() -> str:
    return (
        "This command is local and read-only: it scores the provided JSON only, performs no "
        "network access, writes no files, and does not approve cloning, claiming work, "
        "commenting, opening PRs, logging in, using credentials, touching wallets, or "
        "contacting maintainers."
    )


def _shortlist_safety_boundary_text() -> str:
    return (
        "This shortlist is local and read-only: it scores the provided JSON only, performs no "
        "network access, does not clone repositories, comment, contact maintainers, claim work, "
        "open PRs, log in, use credentials, touch wallets, star repositories, or approve action "
        "without separate human review."
    )


def _search_preview_safety_boundary_text() -> str:
    return (
        "This preview performs only read-only public GitHub API fetches, normalizes and scores "
        "issues in memory, writes no files, and does not approve cloning, claiming work, "
        "commenting, opening PRs, logging in, using credentials, touching wallets, starring "
        "repositories, or contacting maintainers without separate human approval."
    )


def _explain_not_found_message(opportunity_id: str, available_ids: list[str]) -> str:
    ids = ", ".join(available_ids) or "(none)"
    return f"Opportunity id not found: {opportunity_id}\nAvailable IDs: {ids}"


def _render_rank_table(shown: list[dict]) -> str:
    headers = ["Recommendation", "ROI", "Reward", "Title", "Public URL"]
    rows = [_rank_table_row(item) for item in shown]
    widths = [
        max([len(headers[column]), *[len(row[column]) for row in rows]])
        for column in range(len(headers) - 1)
    ]
    lines = [
        _format_rank_table_line(headers, widths),
        _format_rank_table_line(["-" * len(header) for header in headers], widths),
    ]
    lines.extend(_format_rank_table_line(row, widths) for row in rows)
    return "\n".join(lines)


def _rank_table_row(item: dict) -> list[str]:
    score = item.get("score", {})
    roi_score = score.get("roi_score", 0)
    reward = score.get("reward_estimate_usd", 0)
    return [
        str(score.get("recommendation", "")),
        str(roi_score),
        _format_rank_reward(reward),
        _truncate_text(str(item.get("title", "")), 48),
        str(item.get("url") or ""),
    ]


def _format_rank_table_line(cells: list[str], widths: list[int]) -> str:
    padded = [cells[index].ljust(widths[index]) for index in range(len(widths))]
    padded.append(cells[-1])
    return "  ".join(padded).rstrip()


def _format_rank_reward(value: object) -> str:
    if isinstance(value, int | float):
        return f"${int(value):,}"
    return "$0"


def _truncate_text(text: str, max_width: int) -> str:
    if len(text) <= max_width:
        return text
    if max_width <= 3:
        return text[:max_width]
    return text[: max_width - 3].rstrip() + "..."


if __name__ == "__main__":
    raise SystemExit(main())
