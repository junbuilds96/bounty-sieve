from __future__ import annotations

from bounty_sieve.reporting import render_report
from bounty_sieve.scoring import score_opportunity


def test_scoring_handles_malformed_reward_and_tech_without_inflating_score() -> None:
    scored = score_opportunity(
        {
            "id": "edge-malformed-reward",
            "title": "Malformed reward edge case",
            "reward": {"amount": "-100", "currency": "USD", "type": "fixed"},
            "signals": {
                "clarity": "unknown",
                "repo_activity": "unknown",
                "competition": "unknown",
                "complexity": "unknown",
                "scope": "unknown",
                "tech": "python",
            },
        }
    )

    score = scored["score"]
    assert score["reward_estimate_usd"] == 0
    assert score["tech_match"] == 35
    assert score["recommendation"] == "watch"
    assert score["roi_score"] <= 59


def test_scoring_rejects_secret_access_even_with_other_positive_signals() -> None:
    scored = score_opportunity(
        {
            "id": "edge-secret-access",
            "title": "Requires credentialed access",
            "reward": {"amount": 1000, "currency": "USD", "type": "fixed"},
            "signals": {
                "requires_secret_access": True,
                "clarity": "high",
                "repo_activity": "active",
                "competition": "low",
                "complexity": "low",
                "scope": "small",
                "tech": ["python", "pytest", "json"],
            },
        }
    )

    score = scored["score"]
    assert score["recommendation"] == "reject"
    assert score["roi_score"] <= 20
    assert "reject: requires secret, credential, wallet, or private access" in score["reasons"]


def test_report_handles_empty_scored_input() -> None:
    markdown = render_report([])

    assert "- pursue: 0" in markdown
    assert "- watch: 0" in markdown
    assert "- reject: 0" in markdown
    assert "- No pursue recommendations in this run." in markdown
    assert "- No watch or reject recommendations in this run." in markdown
