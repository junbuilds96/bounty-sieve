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
        choices=["fixture", "json", "github-issue", "github-search", "url-list"],
        required=True,
        help=(
            "Discovery source. fixture/json are local only; github-issue, "
            "github-search, and url-list perform explicit read-only public fetches."
        ),
    )
    discover_parser.add_argument("--input", help="Path to a user-provided JSON opportunity file.")
    discover_parser.add_argument("--url", help="Public GitHub issue URL for --source github-issue.")
    discover_parser.add_argument("--query", help="GitHub issue search query for --source github-search.")
    discover_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum GitHub search results for --source github-search; default 10, max 50.",
    )
    discover_parser.add_argument("--out")
    discover_parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Preview github-issue, github-search, or url-list imports as compact JSON without "
            "requiring --out or writing files."
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
        if args.dry_run and args.source not in {"github-issue", "github-search", "url-list"}:
            discover_parser.error(
                "--dry-run can only be used with --source github-issue, --source github-search, or --source url-list"
            )
        if args.dry_run and (args.summary or args.summary_json):
            discover_parser.error("--summary and --summary-json cannot be used with --dry-run")
        if not args.dry_run and not args.out:
            discover_parser.error("the following arguments are required: --out")
        if args.source == "fixture":
            if args.input:
                discover_parser.error("--input can only be used with --source json or --source url-list")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
            opportunities = load_fixture_opportunities()
        elif args.source == "json":
            if not args.input:
                discover_parser.error("--source json requires --input PATH")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
            try:
                opportunities = load_json_opportunities(args.input)
            except OpportunityValidationError as exc:
                discover_parser.error(str(exc))
        elif args.source == "github-issue":
            if args.input:
                discover_parser.error("--input cannot be used with --source github-issue")
            if not args.url:
                discover_parser.error("--source github-issue requires --url URL")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
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
            if args.url:
                discover_parser.error("--url cannot be used with --source github-search")
            if not args.query:
                discover_parser.error("--source github-search requires --query QUERY")
            limit = 10 if args.limit is None else args.limit
            if limit < 1 or limit > 50:
                discover_parser.error("--limit must be between 1 and 50")
            try:
                opportunities = normalize_opportunities(import_github_search(args.query, limit))
            except (GitHubImportError, OpportunityValidationError) as exc:
                discover_parser.error(str(exc))
            if args.dry_run:
                print(json.dumps(opportunities, separators=(",", ":"), sort_keys=True))
                return 0
        else:
            if not args.input:
                discover_parser.error("--source url-list requires --input PATH")
            if args.url:
                discover_parser.error("--url can only be used with --source github-issue")
            if args.query:
                discover_parser.error("--query can only be used with --source github-search")
            if args.limit is not None:
                discover_parser.error("--limit can only be used with --source github-search")
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


def _render_rank_json(ranked: list[dict], shown: list[dict]) -> str:
    payload = {
        "ok": True,
        "total": len(ranked),
        "shown": len(shown),
        "items": [_rank_item_payload(item) for item in shown],
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


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
