"""Deterministic opportunity scoring."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


PAYMENT_CONFIDENCE = {
    "fixed": 85,
    "estimated": 55,
    "conditional": 20,
    "claimed": 10,
}

ISSUE_CLARITY = {
    "high": 90,
    "medium": 60,
    "low": 25,
    "unknown": 35,
}

REPO_ACTIVITY = {
    "active": 85,
    "low": 40,
    "unknown": 20,
}

COMPETITION_RISK = {
    "low": 20,
    "medium": 50,
    "high": 85,
    "unknown": 60,
}

COMPLEXITY_ESTIMATE = {
    "low": 20,
    "medium": 50,
    "high": 85,
    "unknown": 65,
}

SCOPE_RISK = {
    "tiny": 15,
    "small": 25,
    "large": 85,
    "unsafe": 100,
    "unknown": 65,
}

PREFERRED_TECH = {"python", "pytest", "json", "markdown", "cli", "documentation"}


def score_opportunities(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [score_opportunity(opportunity) for opportunity in opportunities]


def score_opportunity(opportunity: dict[str, Any]) -> dict[str, Any]:
    scored = deepcopy(opportunity)
    signals = scored.get("signals", {})
    reward = scored.get("reward", {})

    reward_estimate = _reward_estimate_usd(reward)
    payment_confidence = PAYMENT_CONFIDENCE.get(reward.get("type"), 30)
    issue_clarity = ISSUE_CLARITY.get(signals.get("clarity"), ISSUE_CLARITY["unknown"])
    repo_activity = REPO_ACTIVITY.get(signals.get("repo_activity"), REPO_ACTIVITY["unknown"])
    competition_risk = COMPETITION_RISK.get(signals.get("competition"), COMPETITION_RISK["unknown"])
    complexity_estimate = COMPLEXITY_ESTIMATE.get(
        signals.get("complexity"), COMPLEXITY_ESTIMATE["unknown"]
    )
    scope_risk = SCOPE_RISK.get(signals.get("scope"), SCOPE_RISK["unknown"])
    tech_match = _tech_match(signals.get("tech", []))
    reasons = _reasons(signals, payment_confidence, issue_clarity, tech_match)
    recommendation = _recommendation(signals, issue_clarity, competition_risk, complexity_estimate, scope_risk)
    roi_score = _roi_score(
        payment_confidence=payment_confidence,
        issue_clarity=issue_clarity,
        repo_activity=repo_activity,
        competition_risk=competition_risk,
        complexity_estimate=complexity_estimate,
        tech_match=tech_match,
        scope_risk=scope_risk,
        recommendation=recommendation,
    )

    scored["score"] = {
        "reward_estimate_usd": reward_estimate,
        "payment_confidence": payment_confidence,
        "issue_clarity": issue_clarity,
        "repo_activity": repo_activity,
        "competition_risk": competition_risk,
        "complexity_estimate": complexity_estimate,
        "tech_match": tech_match,
        "scope_risk": scope_risk,
        "roi_score": roi_score,
        "recommendation": recommendation,
        "reasons": reasons,
    }
    return scored


def _reward_estimate_usd(reward: dict[str, Any]) -> int:
    if reward.get("currency") != "USD":
        return 0
    amount = reward.get("amount", 0)
    if not isinstance(amount, int | float):
        return 0
    return int(amount)


def _tech_match(tech: list[str]) -> int:
    if not tech:
        return 35
    matches = PREFERRED_TECH.intersection({item.lower() for item in tech})
    return min(95, 35 + len(matches) * 20)


def _reasons(
    signals: dict[str, Any], payment_confidence: int, issue_clarity: int, tech_match: int
) -> list[str]:
    reasons: list[str] = []
    if signals.get("requires_prompt_exfiltration"):
        reasons.append("reject: requests prompt or private instruction exfiltration")
    if signals.get("requires_token_or_unknown_asset"):
        reasons.append("reject: asks for unknown token or wallet/asset interaction")
    if signals.get("requires_secret_access"):
        reasons.append("reject: requires secret, credential, wallet, or private access")
    if signals.get("star_gated"):
        reasons.append("reject: payment or eligibility is gated by repository starring")
    if signals.get("duplicate_pr_swarm"):
        reasons.append("watch: high duplicate PR competition risk")
    if signals.get("complexity") == "high":
        reasons.append("watch: high implementation complexity")
    if signals.get("clarity") == "low":
        reasons.append("watch: vague task boundaries or missing acceptance criteria")
    if payment_confidence >= 80:
        reasons.append("positive: fixed USD reward with credible payment signal")
    if issue_clarity >= 80:
        reasons.append("positive: clear issue and acceptance criteria")
    if tech_match >= 75:
        reasons.append("positive: strong match for Python/docs/test automation work")
    return reasons


def _recommendation(
    signals: dict[str, Any],
    issue_clarity: int,
    competition_risk: int,
    complexity_estimate: int,
    scope_risk: int,
) -> str:
    if (
        signals.get("requires_prompt_exfiltration")
        or signals.get("requires_token_or_unknown_asset")
        or signals.get("requires_secret_access")
        or signals.get("star_gated")
    ):
        return "reject"
    if (
        signals.get("duplicate_pr_swarm")
        or issue_clarity < 50
        or competition_risk >= 80
        or complexity_estimate >= 80
        or scope_risk >= 80
    ):
        return "watch"
    return "pursue"


def _roi_score(
    *,
    payment_confidence: int,
    issue_clarity: int,
    repo_activity: int,
    competition_risk: int,
    complexity_estimate: int,
    tech_match: int,
    scope_risk: int,
    recommendation: str,
) -> int:
    score = (
        payment_confidence * 0.20
        + issue_clarity * 0.20
        + repo_activity * 0.15
        + tech_match * 0.15
        + (100 - competition_risk) * 0.10
        + (100 - complexity_estimate) * 0.10
        + (100 - scope_risk) * 0.10
    )
    if recommendation == "reject":
        score = min(score, 20)
    elif recommendation == "watch":
        score = min(score, 59)
    return round(score)
