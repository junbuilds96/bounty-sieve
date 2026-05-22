"""Markdown report rendering."""

from __future__ import annotations

from collections import Counter
from typing import Any


RECOMMENDATION_ORDER = ("pursue", "watch", "reject")


def render_report(scored_opportunities: list[dict[str, Any]]) -> str:
    counts = Counter(item["score"]["recommendation"] for item in scored_opportunities)
    top = sorted(
        scored_opportunities,
        key=lambda item: (
            item["score"]["recommendation"] != "pursue",
            -item["score"]["roi_score"],
            item["id"],
        ),
    )
    watch_or_reject = [
        item
        for item in scored_opportunities
        if item["score"]["recommendation"] in {"watch", "reject"}
    ]

    lines = [
        "# Public Bounty Radar Report",
        "",
        "## Safety Boundary",
        "",
        "This offline demo is read-only. It does not clone repositories, open pull requests, connect wallets, use credentials, star repositories, contact maintainers, or attempt prompt/private-data exfiltration.",
        "",
        "## Counts by Recommendation",
        "",
    ]
    for recommendation in RECOMMENDATION_ORDER:
        lines.append(f"- {recommendation}: {counts.get(recommendation, 0)}")

    lines.extend(["", "## Top Opportunities", ""])
    pursue_items = [item for item in top if item["score"]["recommendation"] == "pursue"]
    if pursue_items:
        for item in pursue_items:
            score = item["score"]
            lines.append(
                f"- **{item['title']}** ({item['id']}): ROI {score['roi_score']}, "
                f"${score['reward_estimate_usd']} estimated, confidence {score['payment_confidence']}. "
                f"Next check: confirm issue is still open and unclaimed before any work."
            )
    else:
        lines.append("- No pursue recommendations in this run.")

    lines.extend(["", "## Reject and Watch Reasons", ""])
    if watch_or_reject:
        for item in sorted(watch_or_reject, key=lambda value: (value["score"]["recommendation"], value["id"])):
            score = item["score"]
            reason_text = "; ".join(score["reasons"]) or "No specific reason recorded."
            lines.append(
                f"- **{score['recommendation']}** {item['id']}: {reason_text}"
            )
    else:
        lines.append("- No watch or reject recommendations in this run.")

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
