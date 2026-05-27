"""Report rendering."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any


RECOMMENDATION_ORDER = ("pursue", "watch", "reject")


@dataclass(frozen=True)
class ReportSummary:
    total: int
    counts: Counter[str]
    sentence: str


@dataclass(frozen=True)
class ReportSections:
    summary: ReportSummary
    pursue_items: list[dict[str, Any]]
    watch_items: list[dict[str, Any]]
    rejected_high_reward: list[dict[str, Any]]
    watch_or_reject: list[dict[str, Any]]


def summarize_report(scored_opportunities: list[dict[str, Any]]) -> ReportSummary:
    counts = Counter(item["score"]["recommendation"] for item in scored_opportunities)
    return ReportSummary(
        total=len(scored_opportunities),
        counts=counts,
        sentence=_summary_sentence(len(scored_opportunities), counts),
    )


def render_stdout_summary(
    scored_opportunities: list[dict[str, Any]], report_path: str | Path
) -> str:
    summary = summarize_report(scored_opportunities)
    return "\n".join(
        [
            f"Report: {report_path}",
            f"Total: {summary.total}",
            (
                "Recommendations: "
                f"pursue={summary.counts.get('pursue', 0)}, "
                f"watch={summary.counts.get('watch', 0)}, "
                f"reject={summary.counts.get('reject', 0)}"
            ),
            f"Summary: {summary.sentence}",
        ]
    )


def render_stdout_summary_json(
    scored_opportunities: list[dict[str, Any]], report_path: str | Path
) -> str:
    summary = summarize_report(scored_opportunities)
    payload = {
        "recommendations": {
            recommendation: summary.counts.get(recommendation, 0)
            for recommendation in RECOMMENDATION_ORDER
        },
        "report_path": str(report_path),
        "summary": summary.sentence,
        "total": summary.total,
    }
    return json.dumps(payload, sort_keys=True)


def render_score_stdout_summary(
    scored_opportunities: list[dict[str, Any]], output_path: str | Path
) -> str:
    summary = summarize_report(scored_opportunities)
    return "\n".join(
        [
            f"Output: {output_path}",
            f"Total: {summary.total}",
            (
                "Recommendations: "
                f"pursue={summary.counts.get('pursue', 0)}, "
                f"watch={summary.counts.get('watch', 0)}, "
                f"reject={summary.counts.get('reject', 0)}"
            ),
            f"Summary: {summary.sentence}",
        ]
    )


def render_score_stdout_summary_json(
    scored_opportunities: list[dict[str, Any]], output_path: str | Path
) -> str:
    summary = summarize_report(scored_opportunities)
    payload = {
        "ok": True,
        "output": str(output_path),
        "total": summary.total,
        "recommendations": {
            recommendation: summary.counts.get(recommendation, 0)
            for recommendation in RECOMMENDATION_ORDER
        },
        "summary": summary.sentence,
    }
    return json.dumps(payload, separators=(",", ":"))


def render_report(scored_opportunities: list[dict[str, Any]]) -> str:
    sections = _build_report_sections(scored_opportunities)
    summary = sections.summary
    counts = summary.counts

    lines = [
        "# Bounty Sieve Decision Brief",
        "",
        "## Safety Boundary",
        "",
        "This offline-by-default workflow is read-only. Explicit public URL intake only fetches public metadata. It does not clone repositories, open pull requests, comment, claim work, log in, connect wallets, use credentials, star repositories, contact maintainers, or attempt prompt/private-data exfiltration.",
        "",
        "## Plain-Language Summary",
        "",
        summary.sentence,
        "",
        "## Counts by Recommendation",
        "",
    ]
    for recommendation in RECOMMENDATION_ORDER:
        lines.append(f"- {recommendation}: {counts.get(recommendation, 0)}")

    lines.extend(["", "## Fastest Safe Wins", ""])
    if sections.pursue_items:
        for item in sections.pursue_items:
            score = item["score"]
            lines.append(
                f"- **{item['title']}** ({item['id']}): {_reward_text(score)}, "
                f"ROI {score['roi_score']}, actionability {_actionability_text(score)}. "
                "First safe check: confirm the public issue is still open, unclaimed, and covered by the stated acceptance criteria."
            )
    else:
        lines.append("- No pursue recommendations in this run.")

    lines.extend(["", "## Risky / High-Reward Items", ""])
    if sections.watch_items or sections.rejected_high_reward:
        for item in sections.watch_items:
            score = item["score"]
            lines.append(
                f"- **watch** {item['title']} ({item['id']}): {_reward_text(score)}, "
                f"ROI capped at {score['roi_score']}, actionability {_actionability_text(score)}. "
                f"Check the risk before investing time: {_reason_text(score)}"
            )
        for item in sections.rejected_high_reward:
            score = item["score"]
            lines.append(
                f"- **reject despite reward** {item['title']} ({item['id']}): {_reward_text(score)}. "
                f"Actionability {_actionability_text(score)}. Do not pursue unless the unsafe requirement is removed: {_reason_text(score)}"
            )
    else:
        lines.append("- No watch or high-reward rejected items in this run.")

    lines.extend(["", "## Per-Item Manual Verification Checklist", ""])
    if scored_opportunities:
        for item in sorted(scored_opportunities, key=lambda value: value["id"]):
            score = item["score"]
            lines.extend(
                [
                    f"### {item['title']} ({item['id']})",
                    "",
                    f"- Recommendation: **{score['recommendation']}**; ROI {score['roi_score']}; {_reward_text(score)}.",
                    f"- Actionability: {_actionability_text(score)}. {_actionability_reason_text(score)}",
                    f"- Public page: {_public_page_text(item)}",
                    "- Confirm the opportunity is still open and not already claimed or solved.",
                    "- Confirm payment terms, scope, acceptance criteria, and maintainer or poster activity.",
                    "- Confirm the task does not require credentials, secrets, wallet access, unknown assets, private data, prompt extraction, engagement farming, or duplicate low-value PRs.",
                    f"- Current triage reasons: {_reason_text(score)}",
                    "",
                ]
            )
    else:
        lines.append("- No scored opportunities were provided.")

    lines.extend(["", "## Clear Reject/Watch Reasons", ""])
    if sections.watch_or_reject:
        for item in sections.watch_or_reject:
            score = item["score"]
            lines.append(f"- **{score['recommendation']}** {item['id']}: {_reason_text(score)}")
    else:
        lines.append("- No watch or reject recommendations in this run.")

    lines.extend(
        [
            "",
            "## Agent Handoff",
            "",
            "This generated report is a local decision brief. Agents may only use it to select candidates for human review.",
            "Agents must not clone, comment, submit PRs, connect wallets, use credentials, star repos, claim work, or contact maintainers without explicit human approval.",
        ]
    )

    lines.extend(
        [
            "",
            "## Next Actions",
            "",
            "1. Review pursue items manually in a browser before acting.",
            "2. Verify payment terms, maintainer activity, and whether work is already claimed.",
            "3. Avoid any task that asks for credentials, wallet access, private data, prompt extraction, artificial stars, or duplicate low-value PRs.",
            "4. Keep all discovery read-only until a human explicitly chooses an opportunity.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html_report(scored_opportunities: list[dict[str, Any]]) -> str:
    sections = _build_report_sections(scored_opportunities)
    summary = sections.summary
    counts = summary.counts

    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        "  <title>Bounty Sieve Demo Report</title>",
        "  <style>",
        "    :root { color-scheme: light; --ink: #1d2733; --muted: #637083; --line: #d8dee7; --panel: #f7f9fb; --pursue: #126b4e; --pursue-bg: #e8f5ef; --watch: #8a5a00; --watch-bg: #fff4d8; --reject: #a93434; --reject-bg: #fdeceb; }",
        "    * { box-sizing: border-box; }",
        '    body { margin: 0; color: var(--ink); background: #ffffff; font: 16px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }',
        "    main { width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 32px 0 48px; }",
        "    header { border-bottom: 1px solid var(--line); padding-bottom: 24px; }",
        "    h1 { margin: 0 0 8px; font-size: clamp(2rem, 5vw, 3.2rem); line-height: 1.05; letter-spacing: 0; }",
        "    h2 { margin: 32px 0 12px; font-size: 1.3rem; letter-spacing: 0; }",
        "    h3 { margin: 0 0 8px; font-size: 1rem; letter-spacing: 0; }",
        "    p { margin: 0 0 12px; max-width: 78ch; }",
        "    .note, .muted { color: var(--muted); }",
        "    .counts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 20px; }",
        "    .count, .item, .boundary { border: 1px solid var(--line); border-radius: 8px; padding: 16px; background: var(--panel); }",
        "    .count strong { display: block; font-size: 2.25rem; line-height: 1; }",
        "    .count span { color: var(--muted); text-transform: uppercase; font-size: 0.78rem; letter-spacing: 0.08em; }",
        "    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }",
        "    .item { background: #ffffff; }",
        "    .meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }",
        "    .tag { border-radius: 999px; padding: 3px 9px; font-size: 0.78rem; font-weight: 700; }",
        "    .pursue { color: var(--pursue); background: var(--pursue-bg); }",
        "    .watch { color: var(--watch); background: var(--watch-bg); }",
        "    .reject { color: var(--reject); background: var(--reject-bg); }",
        "    .table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }",
        "    table { width: 100%; border-collapse: collapse; min-width: 760px; }",
        "    th, td { padding: 11px 12px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); }",
        "    th { color: var(--muted); background: var(--panel); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }",
        "    tr:last-child td { border-bottom: 0; }",
        "    @media (max-width: 720px) { main { width: min(100% - 24px, 1120px); padding-top: 24px; } .counts, .grid { grid-template-columns: 1fr; } }",
        "  </style>",
        "</head>",
        "<body>",
        "  <main>",
        "    <header>",
        "      <p class=\"note\">Generated from local scored opportunities. This report is offline, read-only, and contains only supplied or bundled fixture data.</p>",
        "      <h1>Bounty Sieve Demo Report</h1>",
        f"      <p>{_html(summary.sentence)}</p>",
        '      <div class="counts" aria-label="Counts by recommendation">',
    ]
    for recommendation in RECOMMENDATION_ORDER:
        count = counts.get(recommendation, 0)
        lines.extend(
            [
                '        <div class="count">',
                f"          <strong>{count}</strong>",
                f"          <span>{_html(recommendation)}</span>",
                f"          <p>{_html(recommendation)}: {count}</p>",
                "        </div>",
            ]
        )
    lines.extend(
        [
            "      </div>",
            "    </header>",
            "",
            '    <section aria-labelledby="safety-boundary">',
            '      <h2 id="safety-boundary">Safety Boundary</h2>',
            '      <div class="boundary">',
            "        <p>This offline-by-default workflow is read-only. Explicit public URL intake only fetches public metadata. It does not clone repositories, open pull requests, comment, claim work, log in, connect wallets, use credentials, star repositories, contact maintainers, or attempt prompt/private-data exfiltration.</p>",
            "      </div>",
            "    </section>",
            "",
            '    <section aria-labelledby="fastest-safe-wins">',
            '      <h2 id="fastest-safe-wins">Fastest Safe Wins</h2>',
            '      <div class="grid">',
        ]
    )
    if sections.pursue_items:
        for item in sections.pursue_items:
            lines.extend(_render_html_item(item, "pursue"))
    else:
        lines.append('        <p class="muted">No pursue recommendations in this run.</p>')
    lines.extend(
        [
            "      </div>",
            "    </section>",
            "",
            '    <section aria-labelledby="risky-high-reward">',
            '      <h2 id="risky-high-reward">Risky / High-Reward Items</h2>',
            '      <div class="grid">',
        ]
    )
    risky_items = [*sections.watch_items, *sections.rejected_high_reward]
    if risky_items:
        for item in risky_items:
            lines.extend(_render_html_item(item, item["score"]["recommendation"]))
    else:
        lines.append('        <p class="muted">No watch or high-reward rejected items in this run.</p>')
    lines.extend(
        [
            "      </div>",
            "    </section>",
            "",
            '    <section aria-labelledby="all-items">',
            '      <h2 id="all-items">Manual Verification Table</h2>',
            '      <div class="table-wrap">',
            "        <table>",
            "          <thead>",
            "            <tr><th>ID</th><th>Title</th><th>Recommendation</th><th>Actionability</th><th>ROI</th><th>Reward</th><th>Reason</th></tr>",
            "          </thead>",
            "          <tbody>",
        ]
    )
    if scored_opportunities:
        for item in sorted(scored_opportunities, key=lambda value: value["id"]):
            score = item["score"]
            recommendation = score["recommendation"]
            lines.append(
                "            "
                f"<tr><td>{_html(item['id'])}</td><td>{_html(item['title'])}</td>"
                f"<td><span class=\"tag {_html(recommendation)}\">{_html(recommendation)}</span></td>"
                f"<td>{_html(_actionability_text(score))}</td>"
                f"<td>{_html(score['roi_score'])}</td><td>{_html(_reward_text(score))}</td>"
                f"<td>{_html(_reason_text(score))}</td></tr>"
            )
    else:
        lines.append('            <tr><td colspan="7">No scored opportunities were provided.</td></tr>')
    lines.extend(
        [
            "          </tbody>",
            "        </table>",
            "      </div>",
            "    </section>",
            "",
            '    <section aria-labelledby="agent-boundary">',
            '      <h2 id="agent-boundary">Agent Handoff</h2>',
            "      <p>Agents may only use this local report to select candidates for human review. They must not clone, comment, submit PRs, connect wallets, use credentials, star repos, claim work, or contact maintainers without explicit human approval.</p>",
            "    </section>",
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(lines)


def _build_report_sections(scored_opportunities: list[dict[str, Any]]) -> ReportSections:
    summary = summarize_report(scored_opportunities)
    pursue_items = sorted(
        [
            item
            for item in scored_opportunities
            if item["score"]["recommendation"] == "pursue"
        ],
        key=lambda item: (
            _scope_rank(item),
            _complexity_rank(item),
            -item["score"]["roi_score"],
            item["id"],
        ),
    )
    watch_items = sorted(
        [
            item
            for item in scored_opportunities
            if item["score"]["recommendation"] == "watch"
        ],
        key=lambda item: (
            -item["score"]["reward_estimate_usd"],
            -item["score"]["roi_score"],
            item["id"],
        ),
    )
    rejected_high_reward = sorted(
        [
            item
            for item in scored_opportunities
            if item["score"]["recommendation"] == "reject"
            and item["score"]["reward_estimate_usd"] >= 100
        ],
        key=lambda item: (-item["score"]["reward_estimate_usd"], item["id"]),
    )
    watch_or_reject = sorted(
        [
            item
            for item in scored_opportunities
            if item["score"]["recommendation"] in {"watch", "reject"}
        ],
        key=lambda item: (
            item["score"]["recommendation"],
            item["id"],
        ),
    )
    return ReportSections(
        summary=summary,
        pursue_items=pursue_items,
        watch_items=watch_items,
        rejected_high_reward=rejected_high_reward,
        watch_or_reject=watch_or_reject,
    )


def _render_html_item(item: dict[str, Any], recommendation: str) -> list[str]:
    score = item["score"]
    return [
        '        <article class="item">',
        "          <div class=\"meta\">"
        f"<span class=\"tag {_html(recommendation)}\">{_html(recommendation)}</span>"
        f"<span>{_html(_reward_text(score))}</span>"
        f"<span>ROI {_html(score['roi_score'])}</span>"
        f"<span>Actionability {_html(_actionability_text(score))}</span>"
        "</div>",
        f"          <h3>{_html(item['title'])}</h3>",
        f"          <p>{_html(item.get('summary') or 'No summary provided.')}</p>",
        f"          <p class=\"muted\">ID: {_html(item['id'])}</p>",
        f"          <p class=\"muted\">Safe check: {_html(_reason_text(score))}</p>",
        "        </article>",
    ]


def _summary_sentence(total: int, counts: Counter[str]) -> str:
    if total == 0:
        return "No opportunities were scored. Add opportunities first, then rerun scoring and reporting."
    return (
        f"Bounty Sieve reviewed {total} opportunities: {counts.get('pursue', 0)} look worth manual verification, "
        f"{counts.get('watch', 0)} need caution before spending time, and {counts.get('reject', 0)} should be rejected under the current safety rules."
    )


def _reward_text(score: dict[str, Any]) -> str:
    amount = score["reward_estimate_usd"]
    if amount > 0:
        return f"${amount} estimated reward"
    return "no reliable USD reward estimate"


def _reason_text(score: dict[str, Any]) -> str:
    return "; ".join(score["reasons"]) or "No specific reason recorded."


def _actionability_text(score: dict[str, Any]) -> str:
    actionability = score.get("actionability")
    if not isinstance(actionability, dict):
        return "not scored"
    label = actionability.get("label") or "unknown"
    timeliness = actionability.get("timeliness_score")
    confidence = actionability.get("confidence_score")
    return f"{label} (timeliness {timeliness}, confidence {confidence})"


def _actionability_reason_text(score: dict[str, Any]) -> str:
    actionability = score.get("actionability")
    if not isinstance(actionability, dict):
        return "No actionability reason recorded."
    reasons = actionability.get("reasons")
    if not isinstance(reasons, list):
        return "No actionability reason recorded."
    text_reasons = [reason for reason in reasons if isinstance(reason, str)]
    if not text_reasons:
        return "No actionability reason recorded."
    return "; ".join(text_reasons)


def _public_page_text(item: dict[str, Any]) -> str:
    url = item.get("url")
    if isinstance(url, str) and url:
        return url
    return "not provided; locate the public source manually before acting"


def _html(value: object) -> str:
    return escape(str(value), quote=True)


def _scope_rank(item: dict[str, Any]) -> int:
    order = {"tiny": 0, "small": 1, "unknown": 2, "large": 3, "unsafe": 4}
    return order.get(item.get("signals", {}).get("scope", "unknown"), 2)


def _complexity_rank(item: dict[str, Any]) -> int:
    order = {"low": 0, "medium": 1, "unknown": 2, "high": 3}
    return order.get(item.get("signals", {}).get("complexity", "unknown"), 2)
