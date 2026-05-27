from __future__ import annotations

from bounty_sieve.reporting import render_html_report, render_report
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
                "has_acceptance_criteria": True,
                "has_reproduction_steps": True,
                "maintainer_engaged": True,
                "issue_state": "open",
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
    assert score["actionability"]["label"] == "low"
    assert score["actionability"]["confidence_score"] <= 20
    assert "reject: requires secret, credential, wallet, or private access" in score["reasons"]


def test_scoring_penalizes_explicit_repo_health_stale_signal() -> None:
    scored = score_opportunity(
        {
            "id": "edge-stale-repo",
            "title": "Fix docs in stale repo",
            "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
            "signals": {
                "clarity": "high",
                "repo_activity": "low",
                "repo_health_stale": True,
                "competition": "low",
                "complexity": "low",
                "scope": "tiny",
                "tech": ["markdown"],
            },
        }
    )

    score = scored["score"]
    assert score["repo_activity"] == 40
    assert score["recommendation"] == "watch"
    assert score["roi_score"] <= 59
    assert "watch: repository appears stale" in score["reasons"]


def test_actionability_uses_github_and_repo_health_metadata_deterministically() -> None:
    opportunity = {
        "id": "github-example-app-42",
        "title": "Fix public docs bounty",
        "reward": {"amount": 100, "currency": "USD", "type": "fixed"},
        "metadata": {
            "github": {
                "state": "open",
                "updated_at": "2026-05-20T00:00:00Z",
                "observed_at": "2026-05-27T00:00:00Z",
                "assignee_count": 0,
                "repo_health": {
                    "archived": False,
                    "repo_activity": "active",
                    "reason": "repository pushed within 180 days",
                },
            }
        },
        "signals": {
            "clarity": "high",
            "repo_activity": "active",
            "competition": "low",
            "complexity": "low",
            "scope": "tiny",
            "tech": ["markdown"],
            "acceptance_criteria": ["Update README"],
        },
    }

    first = score_opportunity(opportunity)["score"]["actionability"]
    second = score_opportunity(opportunity)["score"]["actionability"]

    assert first == second
    assert first["label"] == "high"
    assert first["timeliness_score"] == 95
    assert first["confidence_score"] == 100
    assert "why now: GitHub issue is open" in first["reasons"]
    assert "why now: issue updated within 14 days" in first["reasons"]
    assert "why now: repository pushed within 180 days" in first["reasons"]
    assert "confidence: acceptance criteria are present" in first["reasons"]


def test_readiness_signals_improve_reasons_without_hiding_assignment_risk() -> None:
    scored = score_opportunity(
        {
            "id": "github-example-app-77",
            "title": "Fix CLI regression",
            "reward": {"amount": 200, "currency": "USD", "type": "fixed"},
            "signals": {
                "clarity": "high",
                "repo_activity": "active",
                "competition": "low",
                "complexity": "low",
                "scope": "tiny",
                "tech": ["python", "pytest"],
                "has_acceptance_criteria": True,
                "has_reproduction_steps": True,
                "maintainer_engaged": True,
                "assigned": True,
                "issue_state": "open",
                "acceptance_criteria": [],
            },
        }
    )

    score = scored["score"]
    actionability = score["actionability"]
    assert score["competition_risk"] == 85
    assert score["recommendation"] == "watch"
    assert "watch: issue already has assignees" in score["reasons"]
    assert "positive: maintainer engagement is visible in comments" in score["reasons"]
    assert "why now: GitHub issue is open" in actionability["reasons"]
    assert "why now: issue already has assignees" in actionability["reasons"]
    assert "confidence: acceptance criteria heading is present" in actionability["reasons"]
    assert "confidence: reproduction or behavior details are present" in actionability["reasons"]
    assert "confidence: maintainer engagement is visible" in actionability["reasons"]


def test_actionability_marks_closed_or_archived_items_low() -> None:
    scored = score_opportunity(
        {
            "id": "github-example-app-99",
            "title": "Closed archived bounty",
            "reward": {"amount": 500, "currency": "USD", "type": "fixed"},
            "metadata": {
                "github": {
                    "state": "closed",
                    "closed_at": "2026-05-01T00:00:00Z",
                    "repo_health": {"archived": True, "repo_activity": "low"},
                }
            },
            "signals": {
                "clarity": "high",
                "repo_activity": "low",
                "repo_archived": True,
                "competition": "low",
                "complexity": "low",
                "scope": "tiny",
                "tech": ["python"],
            },
        }
    )

    actionability = scored["score"]["actionability"]
    assert scored["score"]["recommendation"] == "watch"
    assert actionability["label"] == "low"
    assert actionability["timeliness_score"] == 0
    assert actionability["confidence_score"] <= 35
    assert "why now: GitHub issue is closed" in actionability["reasons"]
    assert "why now: repository is archived" in actionability["reasons"]


def test_report_handles_empty_scored_input() -> None:
    markdown = render_report([])

    assert "# Bounty Sieve Decision Brief" in markdown
    assert "## Plain-Language Summary" in markdown
    assert "- pursue: 0" in markdown
    assert "- watch: 0" in markdown
    assert "- reject: 0" in markdown
    assert "- No pursue recommendations in this run." in markdown
    assert "- No scored opportunities were provided." in markdown
    assert "- No watch or reject recommendations in this run." in markdown
    assert "## Agent Handoff" in markdown
    assert "local decision brief" in markdown
    assert "select candidates for human review" in markdown
    assert "must not clone, comment, submit PRs, connect wallets" in markdown
    assert "use credentials, star repos, claim work, or contact maintainers" in markdown
    assert markdown.index("## Clear Reject/Watch Reasons") < markdown.index("## Agent Handoff")
    assert markdown.index("## Agent Handoff") < markdown.index("## Next Actions")


def test_html_report_escapes_opportunity_content() -> None:
    scored = [
        score_opportunity(
            {
                "id": "safe-html-escape",
                "title": 'Fix <script>alert("x")</script> docs',
                "summary": "Clarify A&B setup <without> private data.",
                "reward": {"amount": 50, "currency": "USD", "type": "fixed"},
                "signals": {
                    "clarity": "high",
                    "repo_activity": "active",
                    "competition": "low",
                    "complexity": "low",
                    "scope": "tiny",
                    "tech": ["markdown"],
                },
            }
        )
    ]

    html = render_html_report(scored)

    assert "<!doctype html>" in html
    assert "Bounty Sieve Demo Report" in html
    assert "Fastest Safe Wins" in html
    assert "Safety Boundary" in html
    assert '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;' in html
    assert "A&amp;B setup &lt;without&gt; private data." in html
    assert '<script>alert("x")</script>' not in html
