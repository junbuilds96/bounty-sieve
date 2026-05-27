"""Deterministic opportunity scoring."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
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
    actionability = _actionability_signal(
        scored,
        signals,
        payment_confidence=payment_confidence,
        issue_clarity=issue_clarity,
        repo_activity=repo_activity,
        competition_risk=competition_risk,
        complexity_estimate=complexity_estimate,
        scope_risk=scope_risk,
        recommendation=recommendation,
    )
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
        "actionability": actionability,
        "reasons": reasons,
    }
    return scored


def _reward_estimate_usd(reward: dict[str, Any]) -> int:
    if reward.get("currency") != "USD":
        return 0
    amount = reward.get("amount", 0)
    if not isinstance(amount, int | float):
        return 0
    if amount <= 0:
        return 0
    return int(amount)


def _tech_match(tech: Any) -> int:
    if not isinstance(tech, list) or not tech:
        return 35
    normalized = {item.lower() for item in tech if isinstance(item, str)}
    matches = PREFERRED_TECH.intersection(normalized)
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
    if signals.get("repo_archived"):
        reasons.append("watch: repository is archived")
    elif signals.get("repo_health_stale"):
        reasons.append("watch: repository appears stale")
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
        or signals.get("repo_archived")
        or signals.get("repo_health_stale")
        or competition_risk >= 80
        or complexity_estimate >= 80
        or scope_risk >= 80
    ):
        return "watch"
    return "pursue"


def _actionability_signal(
    opportunity: dict[str, Any],
    signals: dict[str, Any],
    *,
    payment_confidence: int,
    issue_clarity: int,
    repo_activity: int,
    competition_risk: int,
    complexity_estimate: int,
    scope_risk: int,
    recommendation: str,
) -> dict[str, Any]:
    timeliness_score = 50
    confidence_score = round(
        payment_confidence * 0.20
        + issue_clarity * 0.25
        + repo_activity * 0.15
        + (100 - competition_risk) * 0.15
        + (100 - complexity_estimate) * 0.10
        + (100 - scope_risk) * 0.15
    )
    reasons: list[str] = []

    github_metadata = _github_metadata(opportunity)
    repo_health = _repo_health_metadata(opportunity)

    state = _string_value(github_metadata.get("state"))
    if state == "closed" or _string_value(github_metadata.get("closed_at")):
        timeliness_score = 0
        confidence_score = min(confidence_score, 30)
        reasons.append("why now: GitHub issue is closed")
    elif state == "open":
        timeliness_score += 20
        confidence_score += 5
        reasons.append("why now: GitHub issue is open")
    elif github_metadata:
        confidence_score -= 5
        reasons.append("confidence: GitHub issue state is unavailable")

    updated_at = _parse_timestamp(_string_value(github_metadata.get("updated_at")))
    reference_at = _actionability_reference_timestamp(github_metadata)
    if updated_at is not None and reference_at is not None:
        age_days = (reference_at - updated_at).days
        if age_days <= 14:
            timeliness_score += 15
            reasons.append("why now: issue updated within 14 days")
        elif age_days <= 60:
            timeliness_score += 8
            reasons.append("why now: issue updated within 60 days")
        elif age_days > 180:
            timeliness_score -= 20
            reasons.append("why now: issue has no update within 180 days")
    elif updated_at is not None:
        confidence_score += 2
        reasons.append("confidence: GitHub issue update timestamp is present")

    assignee_count = _non_negative_int(github_metadata.get("assignee_count"))
    if assignee_count and assignee_count > 0:
        timeliness_score -= 25
        confidence_score -= 5
        reasons.append("why now: issue already has assignees")

    if signals.get("duplicate_pr_swarm"):
        timeliness_score -= 20
        confidence_score -= 10
        reasons.append("why now: duplicate PR or claim activity is already visible")

    if signals.get("repo_archived") or repo_health.get("archived") is True:
        timeliness_score = min(timeliness_score, 15)
        confidence_score = min(confidence_score, 35)
        reasons.append("why now: repository is archived")
    elif signals.get("repo_health_stale"):
        timeliness_score -= 25
        confidence_score -= 10
        reasons.append("why now: repository health metadata indicates stale activity")
    elif repo_health:
        repo_health_activity = _string_value(repo_health.get("repo_activity"))
        if repo_health_activity == "active":
            timeliness_score += 10
            confidence_score += 5
            reason = _string_value(repo_health.get("reason"))
            if reason:
                reasons.append(f"why now: {reason}")
            else:
                reasons.append("why now: repository health metadata indicates active work")
        elif repo_health_activity == "low":
            timeliness_score -= 15
            confidence_score -= 5
            reason = _string_value(repo_health.get("reason"))
            if reason:
                reasons.append(f"why now: {reason}")

    acceptance_criteria = signals.get("acceptance_criteria")
    if isinstance(acceptance_criteria, list) and acceptance_criteria:
        confidence_score += 10
        reasons.append("confidence: acceptance criteria are present")
    elif issue_clarity >= 80:
        reasons.append("confidence: issue clarity is high")
    elif issue_clarity < 50:
        confidence_score -= 10
        reasons.append("confidence: issue clarity is low")

    if payment_confidence >= 80:
        reasons.append("confidence: fixed USD reward has a strong payment signal")
    elif payment_confidence < 40:
        confidence_score -= 10
        reasons.append("confidence: payment signal is weak or unknown")

    if recommendation == "reject":
        timeliness_score = min(timeliness_score, 10)
        confidence_score = min(confidence_score, 20)
        reasons.append("why now: current safety rules make this not actionable")
    elif recommendation == "watch":
        timeliness_score = min(timeliness_score, 60)

    timeliness_score = _clamp_score(timeliness_score)
    confidence_score = _clamp_score(confidence_score)
    combined_score = min(timeliness_score, confidence_score)
    label = _actionability_label(combined_score, recommendation)

    if not reasons:
        reasons.append("confidence: limited metadata; manually verify freshness before acting")

    return {
        "label": label,
        "timeliness_score": timeliness_score,
        "confidence_score": confidence_score,
        "reasons": reasons,
    }


def _github_metadata(opportunity: dict[str, Any]) -> dict[str, Any]:
    metadata = opportunity.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    github_metadata = metadata.get("github")
    if not isinstance(github_metadata, dict):
        return {}
    return github_metadata


def _repo_health_metadata(opportunity: dict[str, Any]) -> dict[str, Any]:
    repo_health = _github_metadata(opportunity).get("repo_health")
    if not isinstance(repo_health, dict):
        return {}
    return repo_health


def _actionability_reference_timestamp(github_metadata: dict[str, Any]) -> datetime | None:
    for key in ("observed_at", "fetched_at", "imported_at", "scored_at"):
        parsed = _parse_timestamp(_string_value(github_metadata.get(key)))
        if parsed is not None:
            return parsed
    return None


def _string_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _clamp_score(value: int) -> int:
    return max(0, min(100, value))


def _actionability_label(combined_score: int, recommendation: str) -> str:
    if recommendation == "reject" or combined_score < 40:
        return "low"
    if combined_score >= 70:
        return "high"
    return "medium"


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
