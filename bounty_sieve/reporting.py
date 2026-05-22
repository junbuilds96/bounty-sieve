"""Markdown report rendering."""

from __future__ import annotations

from collections import Counter
from typing import Any


RECOMMENDATION_ORDER = ("pursue", "watch", "reject")


def render_report(scored_opportunities: list[dict[str, Any]]) -> str:
    counts = Counter(item["score"]["recommendation"] for item in scored_opportunities)
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

    lines = [
        "# Bounty Sieve Decision Brief",
        "",
        "## Safety Boundary",
        "",
        "This offline-by-default workflow is read-only. Explicit public URL intake only fetches public metadata. It does not clone repositories, open pull requests, comment, claim work, log in, connect wallets, use credentials, star repositories, contact maintainers, or attempt prompt/private-data exfiltration.",
        "",
        "## Plain-Language Summary",
        "",
        _summary_sentence(len(scored_opportunities), counts),
        "",
        "## Counts by Recommendation",
        "",
    ]
    for recommendation in RECOMMENDATION_ORDER:
        lines.append(f"- {recommendation}: {counts.get(recommendation, 0)}")

    lines.extend(["", "## Fastest Safe Wins", ""])
    if pursue_items:
        for item in pursue_items:
            score = item["score"]
            lines.append(
                f"- **{item['title']}** ({item['id']}): {_reward_text(score)}, "
                f"ROI {score['roi_score']}. First safe check: confirm the public issue is still open, unclaimed, and covered by the stated acceptance criteria."
            )
    else:
        lines.append("- No pursue recommendations in this run.")

    lines.extend(["", "## Risky / High-Reward Items", ""])
    if watch_items or rejected_high_reward:
        for item in watch_items:
            score = item["score"]
            lines.append(
                f"- **watch** {item['title']} ({item['id']}): {_reward_text(score)}, "
                f"ROI capped at {score['roi_score']}. Check the risk before investing time: {_reason_text(score)}"
            )
        for item in rejected_high_reward:
            score = item["score"]
            lines.append(
                f"- **reject despite reward** {item['title']} ({item['id']}): {_reward_text(score)}. "
                f"Do not pursue unless the unsafe requirement is removed: {_reason_text(score)}"
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
    if watch_or_reject:
        for item in watch_or_reject:
            score = item["score"]
            lines.append(f"- **{score['recommendation']}** {item['id']}: {_reason_text(score)}")
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


def _public_page_text(item: dict[str, Any]) -> str:
    url = item.get("url")
    if isinstance(url, str) and url:
        return url
    return "not provided; locate the public source manually before acting"


def _scope_rank(item: dict[str, Any]) -> int:
    order = {"tiny": 0, "small": 1, "unknown": 2, "large": 3, "unsafe": 4}
    return order.get(item.get("signals", {}).get("scope", "unknown"), 2)


def _complexity_rank(item: dict[str, Any]) -> int:
    order = {"low": 0, "medium": 1, "unknown": 2, "high": 3}
    return order.get(item.get("signals", {}).get("complexity", "unknown"), 2)
