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
